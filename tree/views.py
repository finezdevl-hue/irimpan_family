from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, Value, When
from django.db.models import Q
from django.db.models import Sum
from django.utils.dateparse import parse_date
from urllib import error as urlerror, request as urlrequest
from .models import (
    Person,
    Family,
    Event,
    GalleryPhoto,
    SiteAd,
    LiveStreamSettings,
    Committee,
    CommitteeMember,
    MemberGroup,
    HeroImage,
    ClergyMember,
    WhatsAppBroadcast,
    WhatsAppBroadcastRecipient,
    SiteVisitCounter,
)
from .forms import (
    PersonForm,
    FamilyForm,
    MemberCSVUploadForm,
    MemberAccountForm,
    AdminLoginForm,
    EventForm,
    GalleryPhotoForm,
    SiteAdForm,
    LiveStreamSettingsForm,
    CommitteeForm,
    CommitteeMemberForm,
    MemberGroupForm,
    MemberGroupAssignmentForm,
    HeroImageForm,
    ClergyMemberForm,
    WhatsAppBroadcastForm,
)
import csv
import io
import json
import os
import re
from pathlib import Path


def _is_admin_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _is_family_member_user(user):
    return user.is_authenticated and user.groups.filter(name='family_member').exists()


def _can_access_admin_panel(user):
    return _is_admin_user(user) or _is_family_member_user(user)


def _can_manage_members(user):
    return _is_admin_user(user)


def _can_manage_events(user):
    return _is_admin_user(user) or user.has_perm('tree.add_event')


def _can_manage_gallery(user):
    return _is_admin_user(user) or user.has_perm('tree.add_galleryphoto')


def _can_manage_ads(user):
    return _can_access_admin_panel(user)


def _can_manage_live_stream(user):
    return _can_access_admin_panel(user)


def _can_manage_committee(user):
    return _can_access_admin_panel(user)


def _can_manage_whatsapp(user):
    return _is_admin_user(user)


def _can_manage_hero_images(user):
    return _can_access_admin_panel(user)


def _can_manage_clergy(user):
    return _is_admin_user(user)


def _valid_live_streams():
    streams = []
    for stream in LiveStreamSettings.objects.order_by('-is_active', '-updated_at', '-id'):
        if not stream.embed_url:
            continue
        streams.append(stream)
    return streams


def live_stream_context(request):
    active_streams = [stream for stream in _valid_live_streams() if stream.is_active]
    return {
        'nav_live_streams': active_streams,
        'nav_live_stream': active_streams[0] if active_streams else None,
    }


def _normalize_phone_number(phone):
    value = re.sub(r'[^\d+]', '', (phone or '').strip())
    if value.startswith('00'):
        value = f'+{value[2:]}'
    if value and not value.startswith('+'):
        value = f'+{value}'
    digits = re.sub(r'\D', '', value)
    if len(digits) < 8:
        return ''
    return value


def _get_whatsapp_recipients(groups):
    filters = Q()
    if groups:
        filters |= Q(groups__in=groups)
    if not filters:
        return Person.objects.none()
    return Person.objects.filter(filters).distinct().order_by('last_name', 'first_name')


def _send_whatsapp_cloud_message(phone, message_body):
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    api_version = os.getenv('WHATSAPP_API_VERSION', 'v23.0').strip() or 'v23.0'
    if not access_token or not phone_number_id:
        raise RuntimeError('WhatsApp Cloud API is not configured. Add WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID.')

    payload = json.dumps({
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': phone,
        'type': 'text',
        'text': {
            'preview_url': False,
            'body': message_body,
        },
    }).encode('utf-8')
    req = urlrequest.Request(
        url=f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages',
        data=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8') or '{}')
    except urlerror.HTTPError as exc:
        raw_error = exc.read().decode('utf-8', errors='ignore')
        try:
            error_data = json.loads(raw_error)
            error_message = error_data.get('error', {}).get('message') or raw_error
        except json.JSONDecodeError:
            error_message = raw_error or str(exc)
        raise RuntimeError(error_message) from exc
    except urlerror.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc

    message_id = ''
    contacts = response_data.get('messages') or []
    if contacts:
        message_id = contacts[0].get('id', '')
    return message_id


def _admin_context(request, **extra):
    context = {
        'can_manage_members': _can_manage_members(request.user),
        'can_manage_events': _can_manage_events(request.user),
        'can_manage_gallery': _can_manage_gallery(request.user),
        'can_manage_ads': _can_manage_ads(request.user),
        'can_manage_live_stream': _can_manage_live_stream(request.user),
        'can_manage_committee': _can_manage_committee(request.user),
        'can_manage_whatsapp': _can_manage_whatsapp(request.user),
        'can_manage_hero_images': _can_manage_hero_images(request.user),
        'can_manage_clergy': _can_manage_clergy(request.user),
        'is_admin_user': _is_admin_user(request.user),
        'is_family_member_user': _is_family_member_user(request.user),
    }
    context.update(extra)
    return context


admin_required = user_passes_test(_can_access_admin_panel, login_url='admin_login')
members_required = user_passes_test(_can_manage_members, login_url='admin_login')
events_required = user_passes_test(_can_manage_events, login_url='admin_login')
gallery_required = user_passes_test(_can_manage_gallery, login_url='admin_login')
ads_required = user_passes_test(_can_manage_ads, login_url='admin_login')
live_stream_required = user_passes_test(_can_manage_live_stream, login_url='admin_login')
committee_required = user_passes_test(_can_manage_committee, login_url='admin_login')
whatsapp_required = user_passes_test(_can_manage_whatsapp, login_url='admin_login')
hero_images_required = user_passes_test(_can_manage_hero_images, login_url='admin_login')
clergy_required = user_passes_test(_can_manage_clergy, login_url='admin_login')


HOME_ABOUT_BLURB = (
    'Together we have it all and achieve more. Irimpan Kudumba Yogam exists to preserve '
    'family heritage, strengthen unity, and carry shared values into the coming generation.'
)

HISTORY_SECTIONS = [
    {
        'title': 'Roots in Poovathussery',
        'body': (
            'The public family-history notes describe the Irimpan family as settling in '
            'Poovathussery and the wider Parakkadavu area of Aluva taluk in the late 18th century.'
        ),
    },
    {
        'title': 'Migration and Memory',
        'body': (
            'The source history traces the family\'s earlier movement from Alangad and explains '
            'that preserving reliable records across generations has been difficult because many '
            'older church and civil records are incomplete or inaccessible.'
        ),
    },
    {
        'title': 'Work, Faith, and Education',
        'body': (
            'The family history highlights contributions in church life, agriculture, trade, '
            'business, public service, education, science, arts, and community leadership. It also '
            'notes that the family produced clergy and religious sisters across multiple generations.'
        ),
    },
    {
        'title': 'Global Family Presence',
        'body': (
            'The site records family members living and working across major Indian cities as well as '
            'Europe, America, Canada, and West Asia, while still remaining connected to the family home.'
        ),
    },
]

HISTORY_SIGNOFF = {
    'name': 'Irimpan Joseph Babu',
    'role': 'President, Irimpan Kudumba Yogam',
    'note': 'The public history page says the compilation includes details up to January 26, 2023.',
}

CONTACT_DETAILS = {
    'organization': 'Irimpan Kudumba Yogam',
    'address_lines': [
        'Poovathussery, Parakkadavu',
        'Ernakulam district, Kerala - 683579',
    ],
    'website': 'https://www.irimpanfamily.com/',
    'contact_note': 'Share corrections, event updates, and family news with the site administrators.',
}

SOUVENIR_TITLE = 'വലിയവീട് തലമുറ'


SITE_VISIT_COUNTER_KEY = 'public-site'
WHATSAPP_MESSAGE_RESET_KEY = 'whatsapp-message-reset-offset'


def _static_asset_list(*parts):
    base = Path(__file__).resolve().parent / 'static'
    directory = base.joinpath(*parts)
    if not directory.exists():
        return []
    relative_prefix = '/'.join(parts)
    return [
        f'{relative_prefix}/{item.name}'
        for item in sorted(directory.iterdir())
        if item.is_file()
    ]


def home(request):
    people = Person.objects.all()
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    total = people.count()
    generations = max(generation_map.values(), default=0)
    mentors = [
        {
            'name': 'Mar Joseph Irimpan',
            'years': '1919 - 1997',
            'image': 'tree/mentors/mar-joseph-irimpan.jpg',
        },
        {
            'name': 'Fr. Joseph Irimpan',
            'years': '1884 - 1957',
            'image': 'tree/mentors/fr-joseph-irimpan.jpg',
        },
        {
            'name': 'Fr. GeeVarghese Irimpan',
            'years': '1839 - 1917',
            'image': 'tree/mentors/fr-geeverghese-irimpan.jpg',
        },
    ]
    upcoming_events = Event.objects.all()[:3]
    active_ads = [ad for ad in SiteAd.objects.all() if ad.is_scheduled_now]
    popup_ad = next(
        (ad for ad in active_ads if ad.display_type == SiteAd.DISPLAY_POPUP and ad.show_as_popup),
        None,
    )
    side_ads = [ad for ad in active_ads if ad.display_type == SiteAd.DISPLAY_SIDE]
    side_ad = side_ads[0] if side_ads else None
    section_ads = [ad for ad in active_ads if ad.display_type == SiteAd.DISPLAY_SECTION][:3]

    # Fallback: if older ads are still saved as popup-only, keep one visible on the homepage.
    if side_ad is None:
        side_ad = next((ad for ad in active_ads if ad != popup_ad), popup_ad)
        side_ads = [side_ad] if side_ad else []

    if not section_ads:
        section_ads = [ad for ad in active_ads if ad not in {popup_ad, side_ad}][:3]

    hero_images = list(HeroImage.objects.filter(is_active=True))
    if not hero_images:
        hero_images = [
            {'title': 'Hero 1', 'image_url': '/static/tree/home/hero-1.jpg', 'alt_text': 'Family hero image 1'},
            {'title': 'Hero 2', 'image_url': '/static/tree/home/hero-2.jpg', 'alt_text': 'Family hero image 2'},
            {'title': 'Hero 3', 'image_url': '/static/tree/home/hero-3.jpg', 'alt_text': 'Family hero image 3'},
        ]
    return render(request, 'tree/home.html', {
        'people': people,
        'total': total,
        'generations': generations,
        'mentors': mentors,
        'upcoming_events': upcoming_events,
        'popup_ad': popup_ad,
        'side_ad': side_ad,
        'side_ads': side_ads,
        'section_ads': section_ads,
        'hero_images': hero_images,
        'home_about_blurb': HOME_ABOUT_BLURB,
    })


def about(request):
    committees = Committee.objects.filter(is_active=True).prefetch_related('members__person').all()
    return render(request, 'tree/about.html', {
        'committees': committees,
        'history_sections': HISTORY_SECTIONS,
        'history_signoff': HISTORY_SIGNOFF,
    })


def committee_members(request):
    committees = Committee.objects.filter(is_active=True).prefetch_related('members__person').all()
    return render(request, 'tree/committee_members.html', {
        'committees': committees,
    })


def family_page(request):
    families = Family.objects.filter(is_active=True).order_by('name')
    family_cards = []

    for family in families:
        member_count = family.members.count()
        family_cards.append({
            'family': family,
            'photo_url': family.photo.url if family.photo else None,
            'member_count': member_count,
        })
    return render(request, 'tree/family.html', {
        'family_cards': family_cards,
        'total_families': families.count(),
    })


def family_list(request):
    people = list(Person.objects.select_related('family').all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = _build_households(people)

    families = Family.objects.filter(is_active=True).order_by('name').prefetch_related(
        Prefetch('members', queryset=Person.objects.order_by('last_name', 'first_name'))
    )
    family_cards = []
    for family in families:
        family_households = [
            house for house in households
            if house['family_record'] and house['family_record'].pk == family.pk
        ]
        main_household = next((house for house in family_households if not house['is_separate_home']), None)
        separate_households = [house for house in family_households if house['is_separate_home']]
        family_cards.append({
            'family': family,
            'photo_url': family.photo.url if family.photo else None,
            'household_count': len(family_households),
            'member_count': family.members.count(),
            'main_household': main_household,
            'separate_households': separate_households,
        })
    return render(request, 'tree/family_list.html', {
        'family_cards': family_cards,
        'total_families': families.count(),
    })


def separate_homes(request):
    people = list(Person.objects.select_related('family').all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = [house for house in _build_households(people) if house['is_separate_home']]
    return render(request, 'tree/separate_homes.html', {
        'households': households,
        'total_separate_homes': len(households),
    })


def family_record_detail(request, family_pk):
    people = list(Person.objects.select_related('family').all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = _build_households(people)

    family = get_object_or_404(Family, pk=family_pk, is_active=True)
    family_households = [
        house for house in households
        if house['family_record'] and house['family_record'].pk == family.pk
    ]
    main_household = next((house for house in family_households if not house['is_separate_home']), None)
    separate_households = [house for house in family_households if house['is_separate_home']]

    return render(request, 'tree/family_record_detail.html', {
        'family': family,
        'main_household': main_household,
        'separate_households': separate_households,
        'household_count': len(family_households),
    })


def family_detail(request, guardian_pk):
    people = list(Person.objects.select_related('family').all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = _build_households(people)
    house = _find_household(households, guardian_pk)
    if not house:
        guardian = get_object_or_404(Person, pk=guardian_pk)
        return redirect('person_detail', pk=guardian.pk)
    return render(request, 'tree/family_detail.html', {
        'house': house,
        'people': people,
    })


def family_report(request):
    people = list(Person.objects.select_related('family').all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = _build_households(people)
    return render(request, 'tree/family_report.html', {
        'households': households,
        'people': people,
        'total_families': len(households),
        'total_members': len(people),
    })


def events(request):
    upcoming_events = Event.objects.all()
    featured_event = upcoming_events.first()
    remaining_events = upcoming_events[1:] if featured_event else upcoming_events
    return render(request, 'tree/events.html', {
        'upcoming_events': upcoming_events,
        'featured_event': featured_event,
        'remaining_events': remaining_events,
    })


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    other_events = Event.objects.exclude(pk=event.pk)[:3]
    gallery_photos = event.gallery_photos.order_by('created_at')
    return render(request, 'tree/event_detail.html', {
        'event': event,
        'other_events': other_events,
        'gallery_photos': gallery_photos,
    })


def gallery(request):
    gallery_items = GalleryPhoto.objects.order_by('event_id', 'event_name', 'event_date', 'created_at')
    grouped_gallery = []
    for item in gallery_items:
        group_key = item.event_id or f'name-{item.event_name}'
        if grouped_gallery and grouped_gallery[-1]['key'] == group_key:
            grouped_gallery[-1]['photos'].append(item)
            continue
        grouped_gallery.append({
            'key': group_key,
            'event_name': item.event_name,
            'event_date': item.event_date,
            'photos': [item],
        })
    return render(request, 'tree/gallery.html', {
        'gallery_items': gallery_items,
        'grouped_gallery': grouped_gallery,
    })


def contact(request):
    if request.method == 'POST':
        messages.success(request, 'Thanks for reaching out. Your message has been noted for the family team.')
        return redirect('contact')
    return render(request, 'tree/contact.html', {
        'contact_details': CONTACT_DETAILS,
    })


def priests_and_nuns(request):
    clergy_members = ClergyMember.objects.all()
    return render(request, 'tree/priests_and_nuns.html', {
        'clergy_members': clergy_members,
    })


def souvenir_valiyaveedu(request):
    return render(request, 'tree/souvenir_valiyaveedu.html', {
        'souvenir_title': SOUVENIR_TITLE,
        'souvenir_pages': _static_asset_list('tree', 'souvenir', 'valiyaveedu', 'pages'),
        'souvenir_images': _static_asset_list('tree', 'souvenir', 'valiyaveedu'),
    })


def live_stream(request):
    streams = [stream for stream in _valid_live_streams() if stream.is_active]
    selected_stream = None
    selected_stream_id = request.GET.get('stream')
    if selected_stream_id:
        try:
            selected_stream = next(stream for stream in streams if stream.pk == int(selected_stream_id))
        except (StopIteration, TypeError, ValueError):
            selected_stream = None
    if selected_stream is None and streams:
        selected_stream = streams[0]
    return render(request, 'tree/live_stream.html', {
        'stream': selected_stream,
        'streams': streams,
    })


def admin_login(request):
    if _can_access_admin_panel(request.user):
        return redirect('admin_panel')

    form = AdminLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, 'Admin login successful.')
        return redirect('admin_panel')
    return render(request, 'tree/admin_login.html', {'form': form})


@user_passes_test(lambda user: user.is_authenticated)
def admin_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')


@admin_required
def admin_panel(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return render(request, 'tree/admin_dashboard.html', _admin_context(request))

    people_count = Person.objects.count()
    event_count = Event.objects.count()
    ad_count = SiteAd.objects.count()
    live_stream = LiveStreamSettings.objects.order_by('-updated_at', '-id').first()
    live_stream_count = LiveStreamSettings.objects.count()
    committee_count = Committee.objects.count()
    member_group_count = MemberGroup.objects.count()
    hero_image_count = HeroImage.objects.count()
    whatsapp_broadcast_count = WhatsAppBroadcast.objects.count()
    total_whatsapp_message_sent_count = WhatsAppBroadcastRecipient.objects.filter(
        status=WhatsAppBroadcastRecipient.STATUS_SENT
    ).count()
    whatsapp_message_reset_offset = (
        SiteVisitCounter.objects.filter(key=WHATSAPP_MESSAGE_RESET_KEY)
        .values_list('total_visits', flat=True)
        .first()
        or 0
    )
    whatsapp_message_sent_count = max(total_whatsapp_message_sent_count - whatsapp_message_reset_offset, 0)
    site_visit_count = (
        SiteVisitCounter.objects.filter(key=SITE_VISIT_COUNTER_KEY)
        .values_list('total_visits', flat=True)
        .first()
        or 0
    )
    gallery_count = GalleryPhoto.objects.count()
    recent_people = Person.objects.all()[:5]
    recent_events = Event.objects.all()[:5]
    recent_ads = SiteAd.objects.all()[:5]
    recent_gallery = GalleryPhoto.objects.all()[:5]
    return render(request, 'tree/admin_dashboard.html', _admin_context(
        request,
        people_count=people_count,
        event_count=event_count,
        ad_count=ad_count,
        gallery_count=gallery_count,
        recent_people=recent_people,
        recent_events=recent_events,
        recent_ads=recent_ads,
        live_stream=live_stream,
        live_stream_count=live_stream_count,
        committee_count=committee_count,
        member_group_count=member_group_count,
        hero_image_count=hero_image_count,
        whatsapp_broadcast_count=whatsapp_broadcast_count,
        whatsapp_message_sent_count=whatsapp_message_sent_count,
        site_visit_count=site_visit_count,
        recent_gallery=recent_gallery,
    ))


@members_required
def admin_members(request):
    people = Person.objects.select_related('family', 'user').all()
    families = Family.objects.all()
    return render(request, 'tree/admin_members.html', _admin_context(request, people=people, families=families))


@members_required
def admin_families(request):
    families = Family.objects.prefetch_related('members').all()
    return render(request, 'tree/admin_families.html', _admin_context(request, families=families))


@members_required
def admin_family_add(request):
    if request.method == 'POST':
        form = FamilyForm(request.POST, request.FILES)
        if form.is_valid():
            family = form.save()
            messages.success(request, f'{family.name} added successfully.')
            return redirect('admin_families')
    else:
        form = FamilyForm()
    return render(request, 'tree/admin_family_form.html', _admin_context(request, form=form, action='Add'))


@members_required
def admin_family_edit(request, pk):
    family = get_object_or_404(Family, pk=pk)
    if request.method == 'POST':
        form = FamilyForm(request.POST, request.FILES, instance=family)
        if form.is_valid():
            form.save()
            messages.success(request, f'{family.name} updated successfully.')
            return redirect('admin_families')
    else:
        form = FamilyForm(instance=family)
    return render(request, 'tree/admin_family_form.html', _admin_context(request, form=form, action='Edit', family=family))


@members_required
def admin_family_delete(request, pk):
    family = get_object_or_404(Family, pk=pk)
    if request.method == 'POST':
        name = family.name
        family.delete()
        messages.success(request, f'{name} deleted successfully.')
        return redirect('admin_families')
    return render(request, 'tree/admin_family_delete.html', _admin_context(request, family=family))


@members_required
def admin_member_users(request):
    selected_member = None
    if request.method == 'POST':
        form = MemberAccountForm(request.POST)
        if form.is_valid():
            member = form.save()
            if form.cleaned_data.get('allow_dashboard_login'):
                messages.success(request, f'Login account updated for {member.full_name}.')
            else:
                messages.success(request, f'Login access removed for {member.full_name}.')
            return redirect('admin_member_users')
        selected_member = form.cleaned_data.get('member')
    else:
        member_id = request.GET.get('member')
        initial = {}
        if member_id:
            try:
                selected_member = Person.objects.get(pk=member_id)
            except Person.DoesNotExist:
                selected_member = None
        if selected_member:
            initial = {
                'member': selected_member,
                'allow_dashboard_login': bool(selected_member.user),
                'login_username': selected_member.user.username if selected_member.user else '',
            }
        form = MemberAccountForm(initial=initial)

    people = Person.objects.select_related('user').all()
    return render(request, 'tree/admin_member_users.html', _admin_context(
        request,
        form=form,
        people=people,
        selected_member=selected_member,
    ))


@members_required
def admin_member_add(request):
    if request.method == 'POST':
        if 'import_csv' in request.POST:
            csv_upload_form = MemberCSVUploadForm(request.POST, request.FILES)
            form = PersonForm()
            if csv_upload_form.is_valid():
                try:
                    created_count = _import_members_from_csv(csv_upload_form.cleaned_data['csv_file'])
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'{created_count} member{"s" if created_count != 1 else ""} imported successfully.')
                    return redirect('admin_members')
        else:
            form = PersonForm(request.POST, request.FILES)
            csv_upload_form = MemberCSVUploadForm()
            if form.is_valid():
                person = form.save()
                messages.success(request, f'{person.full_name} added successfully.')
                return redirect('admin_members')
    else:
        form = PersonForm()
        csv_upload_form = MemberCSVUploadForm()
    return render(request, 'tree/admin_member_form.html', _admin_context(
        request,
        form=form,
        action='Add',
        csv_upload_form=csv_upload_form,
        csv_expected_headers=_csv_expected_headers(),
    ))


@members_required
def admin_member_edit(request, pk):
    person = get_object_or_404(Person, pk=pk)
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES, instance=person)
        if form.is_valid():
            form.save()
            messages.success(request, f'{person.full_name} updated successfully.')
            return redirect('admin_members')
    else:
        form = PersonForm(instance=person)
    return render(request, 'tree/admin_member_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        person=person,
        csv_upload_form=MemberCSVUploadForm(),
    ))


@members_required
def admin_member_delete(request, pk):
    person = get_object_or_404(Person, pk=pk)
    if request.method == 'POST':
        name = person.full_name
        person.delete()
        messages.success(request, f'{name} deleted successfully.')
        return redirect('admin_members')
    return render(request, 'tree/admin_member_delete.html', _admin_context(request, person=person))


@members_required
def admin_members_clear_all(request):
    member_count = Person.objects.count()
    if request.method == 'POST':
        if member_count:
            Person.objects.all().delete()
            messages.success(request, f'All {member_count} members were deleted successfully.')
        else:
            messages.info(request, 'There were no members to delete.')
        return redirect('admin_members')
    return render(request, 'tree/admin_clear_members.html', _admin_context(
        request,
        member_count=member_count,
    ))


@members_required
def admin_member_segments(request):
    groups = MemberGroup.objects.prefetch_related('people').all()
    return render(request, 'tree/admin_member_segments.html', _admin_context(
        request,
        groups=groups,
    ))


@hero_images_required
def admin_hero_images(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return redirect('admin_hero_image_add')
    hero_images = HeroImage.objects.all()
    return render(request, 'tree/admin_hero_images.html', _admin_context(request, hero_images=hero_images))


@hero_images_required
def admin_hero_image_add(request):
    if request.method == 'POST':
        form = HeroImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save()
            messages.success(request, f'{image.title} hero image added successfully.')
            return redirect('admin_hero_images')
    else:
        form = HeroImageForm()
    return render(request, 'tree/admin_hero_image_form.html', _admin_context(request, form=form, action='Add'))


@hero_images_required
def admin_hero_image_edit(request, pk):
    hero_image = get_object_or_404(HeroImage, pk=pk)
    if request.method == 'POST':
        form = HeroImageForm(request.POST, request.FILES, instance=hero_image)
        if form.is_valid():
            form.save()
            messages.success(request, f'{hero_image.title} hero image updated successfully.')
            return redirect('admin_hero_images')
    else:
        form = HeroImageForm(instance=hero_image)
    return render(request, 'tree/admin_hero_image_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        hero_image=hero_image,
    ))


@hero_images_required
def admin_hero_image_delete(request, pk):
    hero_image = get_object_or_404(HeroImage, pk=pk)
    if request.method == 'POST':
        title = hero_image.title
        hero_image.delete()
        messages.success(request, f'{title} hero image deleted successfully.')
        return redirect('admin_hero_images')
    return render(request, 'tree/admin_hero_image_delete.html', _admin_context(request, hero_image=hero_image))


@clergy_required
def admin_clergy_members(request):
    clergy_members = ClergyMember.objects.all()
    return render(request, 'tree/admin_clergy_members.html', _admin_context(request, clergy_members=clergy_members))


@clergy_required
def admin_clergy_member_add(request):
    form = ClergyMemberForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Clergy member added successfully.')
        return redirect('admin_clergy_members')
    return render(request, 'tree/admin_clergy_member_form.html', _admin_context(request, form=form, action='Add'))


@clergy_required
def admin_clergy_member_edit(request, pk):
    clergy_member = get_object_or_404(ClergyMember, pk=pk)
    form = ClergyMemberForm(request.POST or None, request.FILES or None, instance=clergy_member)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Clergy member updated successfully.')
        return redirect('admin_clergy_members')
    return render(request, 'tree/admin_clergy_member_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        clergy_member=clergy_member,
    ))


@clergy_required
def admin_clergy_member_delete(request, pk):
    clergy_member = get_object_or_404(ClergyMember, pk=pk)
    if request.method == 'POST':
        clergy_member.delete()
        messages.success(request, 'Clergy member deleted successfully.')
        return redirect('admin_clergy_members')
    return render(request, 'tree/admin_clergy_member_delete.html', _admin_context(request, clergy_member=clergy_member))


@members_required
def admin_member_group_add(request):
    if request.method == 'POST':
        form = MemberGroupForm(request.POST)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'{group.name} group added successfully.')
            return redirect('admin_member_segments')
    else:
        form = MemberGroupForm()
    return render(request, 'tree/admin_member_segment_form.html', _admin_context(
        request,
        form=form,
        action='Add',
        segment_type='Group',
    ))


@members_required
def admin_member_group_edit(request, pk):
    segment = get_object_or_404(MemberGroup, pk=pk)
    if request.method == 'POST':
        form = MemberGroupForm(request.POST, instance=segment)
        if form.is_valid():
            form.save()
            messages.success(request, f'{segment.name} group updated successfully.')
            return redirect('admin_member_segments')
    else:
        form = MemberGroupForm(instance=segment)
    return render(request, 'tree/admin_member_segment_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        segment_type='Group',
        segment=segment,
    ))


@members_required
def admin_member_group_delete(request, pk):
    segment = get_object_or_404(MemberGroup, pk=pk)
    if request.method == 'POST':
        name = segment.name
        segment.delete()
        messages.success(request, f'{name} group deleted successfully.')
        return redirect('admin_member_segments')
    return render(request, 'tree/admin_member_segment_delete.html', _admin_context(
        request,
        segment=segment,
        segment_type='Group',
    ))


@members_required
def admin_member_group_members(request, pk):
    segment = get_object_or_404(MemberGroup, pk=pk)
    if request.method == 'POST':
        form = MemberGroupAssignmentForm(request.POST)
        if form.is_valid():
            segment.people.set(form.cleaned_data['people'])
            messages.success(request, f'Members updated for {segment.name} group.')
            return redirect('admin_member_segments')
    else:
        form = MemberGroupAssignmentForm(initial={'people': segment.people.all()})
    return render(request, 'tree/admin_member_segment_members.html', _admin_context(
        request,
        form=form,
        segment=segment,
        segment_type='Group',
    ))


@members_required
def admin_member_group_member_remove(request, pk, person_pk):
    segment = get_object_or_404(MemberGroup, pk=pk)
    person = get_object_or_404(Person, pk=person_pk)
    if request.method == 'POST':
        segment.people.remove(person)
        messages.success(request, f'{person.full_name} removed from {segment.name} group.')
        return redirect('admin_member_group_members', pk=segment.pk)
    return render(request, 'tree/admin_member_segment_member_remove.html', _admin_context(
        request,
        segment=segment,
        person=person,
        segment_type='Group',
    ))


@whatsapp_required
def admin_whatsapp_broadcast(request):
    preview_recipients = []
    if request.method == 'POST':
        form = WhatsAppBroadcastForm(request.POST)
        if form.is_valid():
            groups = list(form.cleaned_data['target_groups'])
            recipients = list(_get_whatsapp_recipients(groups))
            preview_recipients = recipients[:12]

            if not recipients:
                form.add_error(None, 'No members matched the selected groups.')
            else:
                broadcast = form.save(commit=False)
                broadcast.created_by = request.user
                broadcast.status = WhatsAppBroadcast.STATUS_DRAFT
                broadcast.save()
                form.save_m2m()

                sent_count = 0
                failed_count = 0
                for recipient in recipients:
                    normalized_phone = _normalize_phone_number(recipient.phone)
                    log = WhatsAppBroadcastRecipient.objects.create(
                        broadcast=broadcast,
                        person=recipient,
                        phone=normalized_phone or recipient.phone,
                    )
                    if not normalized_phone:
                        log.status = WhatsAppBroadcastRecipient.STATUS_FAILED
                        log.error_message = 'Missing or invalid phone number.'
                        log.save(update_fields=['status', 'error_message', 'updated_at'])
                        failed_count += 1
                        continue

                    try:
                        provider_message_id = _send_whatsapp_cloud_message(normalized_phone, broadcast.message)
                    except RuntimeError as exc:
                        log.status = WhatsAppBroadcastRecipient.STATUS_FAILED
                        log.error_message = str(exc)
                        log.save(update_fields=['status', 'error_message', 'updated_at'])
                        failed_count += 1
                    else:
                        log.status = WhatsAppBroadcastRecipient.STATUS_SENT
                        log.provider_message_id = provider_message_id
                        log.save(update_fields=['status', 'provider_message_id', 'updated_at'])
                        sent_count += 1

                broadcast.sent_count = sent_count
                broadcast.failed_count = failed_count
                broadcast.status = WhatsAppBroadcast.STATUS_SENT if sent_count and not failed_count else (
                    WhatsAppBroadcast.STATUS_FAILED if failed_count and not sent_count else WhatsAppBroadcast.STATUS_SENT
                )
                broadcast.save(update_fields=['sent_count', 'failed_count', 'status', 'updated_at'])
                messages.success(request, f'WhatsApp broadcast finished. Sent: {sent_count}, Failed: {failed_count}.')
                return redirect('admin_whatsapp_broadcast')
    else:
        form = WhatsAppBroadcastForm()

    recent_broadcasts = WhatsAppBroadcast.objects.prefetch_related('target_groups').all()[:10]
    provider_ready = bool(os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip() and os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip())
    return render(request, 'tree/admin_whatsapp_broadcast.html', _admin_context(
        request,
        form=form,
        preview_recipients=preview_recipients,
        recent_broadcasts=recent_broadcasts,
        provider_ready=provider_ready,
    ))


@events_required
def admin_events(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return redirect('admin_event_add')
    events = Event.objects.all()
    return render(request, 'tree/admin_events.html', _admin_context(request, events=events))


@gallery_required
def admin_gallery(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return redirect('admin_gallery_add')
    gallery_items = GalleryPhoto.objects.all()
    return render(request, 'tree/admin_gallery.html', _admin_context(request, gallery_items=gallery_items))


@ads_required
def admin_ads(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return redirect('admin_ad_add')
    ads = SiteAd.objects.select_related('created_by').all()
    return render(request, 'tree/admin_ads.html', _admin_context(request, ads=ads))


@live_stream_required
def admin_live_stream(request):
    stream = None
    if request.method == 'POST':
        form = LiveStreamSettingsForm(request.POST)
        if form.is_valid():
            stream = form.save()
            messages.success(request, f'{stream.title} live stream added successfully.')
            return redirect('admin_live_stream')
    else:
        form = LiveStreamSettingsForm()
    streams = LiveStreamSettings.objects.annotate(
        status_order=Case(
            When(is_active=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by('status_order', '-updated_at', '-id')
    return render(request, 'tree/admin_live_stream_form.html', _admin_context(
        request,
        form=form,
        stream=stream,
        streams=streams,
        form_mode='add',
    ))


@live_stream_required
def admin_live_stream_edit(request, pk):
    stream = get_object_or_404(LiveStreamSettings, pk=pk)
    if request.method == 'POST':
        form = LiveStreamSettingsForm(request.POST, instance=stream)
        if form.is_valid():
            stream = form.save()
            messages.success(request, f'{stream.title} live stream updated successfully.')
            return redirect('admin_live_stream')
    else:
        form = LiveStreamSettingsForm(instance=stream)
    streams = LiveStreamSettings.objects.annotate(
        status_order=Case(
            When(is_active=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by('status_order', '-updated_at', '-id')
    return render(request, 'tree/admin_live_stream_form.html', _admin_context(
        request,
        form=form,
        stream=stream,
        streams=streams,
        form_mode='edit',
    ))


@live_stream_required
def admin_live_stream_delete(request, pk):
    stream = get_object_or_404(LiveStreamSettings, pk=pk)
    if request.method == 'POST':
        title = stream.title
        stream.delete()
        messages.success(request, f'{title} live stream deleted successfully.')
        return redirect('admin_live_stream')
    return render(request, 'tree/admin_live_stream_delete.html', _admin_context(request, stream=stream))


@committee_required
def admin_committees(request):
    if _is_family_member_user(request.user) and not _is_admin_user(request.user):
        return redirect('admin_committee_add')
    committees = Committee.objects.prefetch_related('members').all()
    return render(request, 'tree/admin_committees.html', _admin_context(request, committees=committees))


@committee_required
def admin_committee_add(request):
    if request.method == 'POST':
        form = CommitteeForm(request.POST)
        if form.is_valid():
            committee = form.save()
            messages.success(request, f'{committee.year} committee added successfully.')
            return redirect('admin_committees')
    else:
        form = CommitteeForm()
    return render(request, 'tree/admin_committee_form.html', _admin_context(request, form=form, action='Add'))


@committee_required
def admin_committee_edit(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    if request.method == 'POST':
        form = CommitteeForm(request.POST, instance=committee)
        if form.is_valid():
            form.save()
            messages.success(request, f'{committee.year} committee updated successfully.')
            return redirect('admin_committees')
    else:
        form = CommitteeForm(instance=committee)
    return render(request, 'tree/admin_committee_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        committee=committee,
    ))


@committee_required
def admin_committee_delete(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    if request.method == 'POST':
        year = committee.year
        committee.delete()
        messages.success(request, f'{year} committee deleted successfully.')
        return redirect('admin_committees')
    return render(request, 'tree/admin_committee_delete.html', _admin_context(request, committee=committee))


@committee_required
def admin_committee_member_add(request):
    if request.method == 'POST':
        form = CommitteeMemberForm(request.POST, request.FILES)
        if form.is_valid():
            member = form.save()
            messages.success(request, f'{member.name} added to {member.committee.year} committee successfully.')
            return redirect('admin_committees')
    else:
        initial = {}
        committee_id = request.GET.get('committee')
        if committee_id:
            initial['committee'] = committee_id
        form = CommitteeMemberForm(initial=initial)
    return render(request, 'tree/admin_committee_member_form.html', _admin_context(request, form=form, action='Add'))


@committee_required
def admin_committee_member_edit(request, pk):
    member = get_object_or_404(CommitteeMember, pk=pk)
    if request.method == 'POST':
        form = CommitteeMemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, f'{member.name} updated successfully.')
            return redirect('admin_committees')
    else:
        form = CommitteeMemberForm(instance=member)
    return render(request, 'tree/admin_committee_member_form.html', _admin_context(
        request,
        form=form,
        action='Edit',
        committee_member=member,
    ))


@committee_required
def admin_committee_member_delete(request, pk):
    member = get_object_or_404(CommitteeMember, pk=pk)
    if request.method == 'POST':
        name = member.name
        member.delete()
        messages.success(request, f'{name} removed from the committee.')
        return redirect('admin_committees')
    return render(request, 'tree/admin_committee_member_delete.html', _admin_context(request, committee_member=member))


@ads_required
def admin_ad_add(request):
    if request.method == 'POST':
        form = SiteAdForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.created_by = request.user
            ad.save()
            messages.success(request, f'{ad.title} ad posted successfully.')
            return redirect('admin_ads')
    else:
        form = SiteAdForm()
    return render(request, 'tree/admin_ad_form.html', _admin_context(request, form=form, action='Add'))


@members_required
def admin_ad_edit(request, pk):
    ad = get_object_or_404(SiteAd, pk=pk)
    if request.method == 'POST':
        form = SiteAdForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            form.save()
            messages.success(request, f'{ad.title} ad updated successfully.')
            return redirect('admin_ads')
    else:
        form = SiteAdForm(instance=ad)
    return render(request, 'tree/admin_ad_form.html', _admin_context(request, form=form, action='Edit', ad=ad))


@members_required
def admin_ad_delete(request, pk):
    ad = get_object_or_404(SiteAd, pk=pk)
    if request.method == 'POST':
        title = ad.title
        ad.delete()
        messages.success(request, f'{title} ad deleted successfully.')
        return redirect('admin_ads')
    return render(request, 'tree/admin_ad_delete.html', _admin_context(request, ad=ad))


@gallery_required
def admin_gallery_add(request):
    if request.method == 'POST':
        form = GalleryPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            multiple_images = request.FILES.getlist('images')
            single_image = form.cleaned_data.get('image')
            uploaded_images = [img for img in multiple_images if img]
            if single_image:
                uploaded_images.append(single_image)

            if not uploaded_images:
                form.add_error('images', 'Please upload at least one image.')
            else:
                base = form.save(commit=False)
                saved_count = 0
                for index, uploaded_image in enumerate(uploaded_images, start=1):
                    item = GalleryPhoto(
                        title=base.title if len(uploaded_images) == 1 else f'{base.title} {index}',
                        event=base.event,
                        event_name=base.event_name,
                        event_date=base.event_date,
                        caption=base.caption,
                        image=uploaded_image,
                    )
                    item.save()
                    saved_count += 1
                messages.success(request, f'{saved_count} gallery photo{"s" if saved_count != 1 else ""} added successfully.')
                return redirect('admin_gallery')
    else:
        form = GalleryPhotoForm()
    return render(request, 'tree/admin_gallery_form.html', _admin_context(request, form=form, action='Add'))


@members_required
def admin_gallery_edit(request, pk):
    item = get_object_or_404(GalleryPhoto, pk=pk)
    if request.method == 'POST':
        form = GalleryPhotoForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f'{item.title} updated successfully.')
            return redirect('admin_gallery')
    else:
        form = GalleryPhotoForm(instance=item)
    return render(request, 'tree/admin_gallery_form.html', _admin_context(request, form=form, action='Edit', item=item))


@members_required
def admin_gallery_delete(request, pk):
    item = get_object_or_404(GalleryPhoto, pk=pk)
    if request.method == 'POST':
        title = item.title
        item.delete()
        messages.success(request, f'{title} removed from the gallery.')
        return redirect('admin_gallery')
    return render(request, 'tree/admin_gallery_delete.html', _admin_context(request, item=item))


@events_required
def admin_event_add(request):
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            messages.success(request, f'{event.title} added successfully.')
            return redirect('admin_events')
    else:
        form = EventForm()
    return render(request, 'tree/admin_event_form.html', _admin_context(request, form=form, action='Add'))


@members_required
def admin_event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, f'{event.title} updated successfully.')
            return redirect('admin_events')
    else:
        form = EventForm(instance=event)
    return render(request, 'tree/admin_event_form.html', _admin_context(request, form=form, action='Edit', event=event))


@members_required
def admin_event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        title = event.title
        event.delete()
        messages.success(request, f'{title} deleted successfully.')
        return redirect('admin_events')
    return render(request, 'tree/admin_event_delete.html', _admin_context(request, event=event))


def tree_view(request):
    people = Person.objects.all()
    family_names = Family.objects.filter(is_active=True).order_by('name')
    return render(request, 'tree/tree.html', {'people': people, 'family_names': family_names})


def tree_data(request):
    people = list(Person.objects.all())
    _apply_generations(people, _generation_map(people))
    nodes = []
    edges = []
    seen_spouse_edges = set()

    for p in people:
        nodes.append(p.to_dict())
        if p.father_id:
            edges.append({'from': p.father_id, 'to': p.pk, 'type': 'parent'})
        if p.mother_id:
            edges.append({'from': p.mother_id, 'to': p.pk, 'type': 'parent'})
        for spouse in p.get_spouses():
            key = tuple(sorted((p.pk, spouse.pk)))
            if key in seen_spouse_edges:
                continue
            seen_spouse_edges.add(key)
            edges.append({'from': key[0], 'to': key[1], 'type': 'spouse'})

    return JsonResponse({'nodes': nodes, 'edges': edges})


def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    children = person.get_children()
    siblings = person.get_siblings()
    spouses = person.get_spouses()
    generation_map = _generation_map(Person.objects.all())
    _apply_generations([person, *children, *siblings, *spouses], generation_map)
    if person.father:
        person.father._generation = generation_map.get(person.father_id, 1)
    if person.mother:
        person.mother._generation = generation_map.get(person.mother_id, 1)
    for spouse in spouses:
        spouse._generation = generation_map.get(spouse.pk, 1)
    return render(request, 'tree/person_detail.html', {
        'person': person,
        'children': children,
        'siblings': siblings,
        'spouses': spouses,
    })


@members_required
def person_add(request):
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES)
        if form.is_valid():
            person = form.save()
            messages.success(request, f'{person.full_name} added to the family tree!')
            return redirect('person_detail', pk=person.pk)
    else:
        form = PersonForm()
    return render(request, 'tree/person_form.html', {'form': form, 'action': 'Add'})


@members_required
def person_edit(request, pk):
    person = get_object_or_404(Person, pk=pk)
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES, instance=person)
        if form.is_valid():
            person = form.save()
            messages.success(request, f'{person.full_name} updated successfully!')
            return redirect('person_detail', pk=person.pk)
    else:
        form = PersonForm(instance=person)
    return render(request, 'tree/person_form.html', {'form': form, 'action': 'Edit', 'person': person})


@members_required
def person_delete(request, pk):
    person = get_object_or_404(Person, pk=pk)
    if request.method == 'POST':
        name = person.full_name
        person.delete()
        messages.success(request, f'{name} removed from the family tree.')
        return redirect('home')
    return render(request, 'tree/person_confirm_delete.html', {'person': person})


def people_list(request):
    q = request.GET.get('q', '')
    people = Person.objects.all()
    if q:
        people = people.filter(first_name__icontains=q) | people.filter(last_name__icontains=q)
    _apply_generations(people, _generation_map(Person.objects.all()))
    return render(request, 'tree/people_list.html', {'people': people, 'q': q})


def _generation_map(people):
    people = list(people)
    if not people:
        return {}

    parents = {
        person.pk: tuple(parent_id for parent_id in (person.father_id, person.mother_id) if parent_id)
        for person in people
    }
    memo = {}

    def get_depth(person_id):
        if person_id in memo:
            return memo[person_id]
        parent_ids = parents.get(person_id, ())
        if not parent_ids:
            memo[person_id] = 1
            return 1
        memo[person_id] = max(get_depth(parent_id) for parent_id in parent_ids) + 1
        return memo[person_id]

    return {person.pk: get_depth(person.pk) for person in people}


def _apply_generations(people, generation_map):
    for person in people:
        person._generation = generation_map.get(person.pk, 1)


def _site_stats():
    people = Person.objects.all()
    generation_map = _generation_map(people)
    return {
        'total_members': people.count(),
        'total_generations': max(generation_map.values(), default=0),
        'living_members': sum(1 for person in people if person.is_alive),
    }


def _build_households(people):
    people = list(people)
    if not people:
        return []

    people_by_id = {person.pk: person for person in people}
    children_map = {person.pk: [] for person in people}
    for person in people:
        for parent_id in {person.father_id, person.mother_id}:
            if parent_id in children_map and person not in children_map[parent_id]:
                children_map[parent_id].append(person)

    for child_list in children_map.values():
        child_list.sort(key=lambda member: (member.generation, member.last_name.lower(), member.first_name.lower(), member.pk))

    candidate_ids = {
        person.pk for person in people
        if person.living_separately or (not person.father_id and not person.mother_id)
    }

    def person_sort_key(person):
        return (person.generation, person.last_name.lower(), person.first_name.lower(), person.pk)

    def choose_guardian(person, spouse=None):
        pair = [member for member in (person, spouse) if member]
        male_guardian = next((member for member in pair if member.gender == 'M'), None)
        if male_guardian:
            return male_guardian
        return sorted(pair, key=person_sort_key)[0]

    def add_house_member(person, member_ids, visited, house_root_ids):
        if not person or person.pk in visited:
            return

        visited.add(person.pk)
        member_ids.append(person.pk)

        spouse = people_by_id.get(person.spouse_id)
        if spouse and not spouse.living_separately and spouse.pk not in house_root_ids:
            add_house_member(spouse, member_ids, visited, house_root_ids)

        for child in children_map.get(person.pk, []):
            if child.living_separately:
                continue
            add_house_member(child, member_ids, visited, house_root_ids)

    households = []
    seen_house_keys = set()

    for person in sorted(people, key=person_sort_key):
        if person.pk not in candidate_ids:
            continue

        spouse = people_by_id.get(person.spouse_id)
        house_root_ids = {person.pk}
        if spouse and spouse.pk in candidate_ids:
            house_root_ids.add(spouse.pk)

        house_key = tuple(sorted(house_root_ids))
        if house_key in seen_house_keys:
            continue
        seen_house_keys.add(house_key)

        guardian = choose_guardian(person, spouse if spouse and spouse.pk in house_root_ids else None)
        partner = None
        if guardian.spouse_id in people_by_id and guardian.spouse_id in house_root_ids:
            partner = people_by_id[guardian.spouse_id]
        elif spouse and spouse.pk in house_root_ids and spouse.pk != guardian.pk:
            partner = spouse

        member_ids = []
        visited = set()
        add_house_member(guardian, member_ids, visited, house_root_ids)
        if partner:
            add_house_member(partner, member_ids, visited, house_root_ids)

        members = [people_by_id[member_id] for member_id in member_ids if member_id in people_by_id]
        member_rows = [{'person': guardian, 'role': 'Head'}]
        if partner and partner.pk != guardian.pk:
            member_rows.append({'person': partner, 'role': 'Spouse'})
        seen_member_ids = {row['person'].pk for row in member_rows}
        for member in members:
            if member.pk in seen_member_ids:
                continue
            member_rows.append({'person': member, 'role': 'Child'})
            seen_member_ids.add(member.pk)
        assigned_family = next(
            (member.family for member in [guardian, partner, *members] if member and member.family_id),
            None,
        )
        if guardian.living_separately:
            display_name = f'{guardian.full_name} & Family'
        else:
            base_name = assigned_family.name if assigned_family else (guardian.last_name or (partner.last_name if partner else guardian.full_name))
            display_name = f'{base_name} & Family'
        children = [member for member in members if member.pk != guardian.pk and (not partner or member.pk != partner.pk)]
        house_photo = None
        house_photo_alt = guardian.full_name
        if guardian.living_separately and guardian.family_photo:
            house_photo = guardian.family_photo.url
            house_photo_alt = f"{guardian.full_name} family photo"
        elif partner and partner.family_photo:
            house_photo = partner.family_photo.url
            house_photo_alt = f"{partner.full_name} family photo"
        elif assigned_family and assigned_family.photo:
            house_photo = assigned_family.photo.url
            house_photo_alt = assigned_family.name
        elif guardian.photo:
            house_photo = guardian.photo.url
            house_photo_alt = guardian.full_name
        elif partner and partner.photo:
            house_photo = partner.photo.url
            house_photo_alt = partner.full_name
        households.append({
            'guardian': guardian,
            'partner': partner,
            'members': members,
            'children': children,
            'resident_count': len(members),
            'family_name': assigned_family.name if assigned_family else (guardian.last_name or (partner.last_name if partner else 'Family')),
            'family_bio': assigned_family.bio if assigned_family else '',
            'family_record': assigned_family,
            'family_photo_url': house_photo,
            'family_photo_alt': house_photo_alt,
            'is_separate_home': guardian.living_separately,
            'house_key': guardian.pk,
            'member_rows': member_rows,
            'display_name': display_name,
        })

    households.sort(key=lambda house: person_sort_key(house['guardian']))
    return households


def _find_household(households, guardian_pk):
    for house in households:
        if house['guardian'].pk == guardian_pk:
            return house
    return None


def _csv_expected_headers():
    return [
        'key',
        'first_name',
        'last_name',
        'family_name',
        'family_id',
        'gender',
        'birth_date',
        'death_date',
        'birth_place',
        'email',
        'phone',
        'blood_group',
        'current_address',
        'living_separately',
        'bio',
        'father_key',
        'mother_key',
        'spouse_key',
        'father_id',
        'mother_id',
        'spouse_id',
    ]


def _import_members_from_csv(uploaded_file):
    try:
        text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('CSV file must be UTF-8 encoded.') from exc

    reader = csv.DictReader(io.StringIO(text))
    expected_headers = set(_csv_expected_headers())
    received_headers = {header.strip() for header in (reader.fieldnames or []) if header and header.strip()}
    missing_headers = [header for header in ('first_name',) if header not in received_headers]
    unknown_headers = sorted(received_headers - expected_headers)

    if not reader.fieldnames:
        raise ValueError('CSV file is empty or missing a header row.')
    if missing_headers:
        raise ValueError(f'Missing required CSV header(s): {", ".join(missing_headers)}.')
    if unknown_headers:
        raise ValueError(f'Unsupported CSV header(s): {", ".join(unknown_headers)}.')

    rows = list(reader)
    if not rows:
        raise ValueError('CSV file has no member rows to import.')

    created_people_by_key = {}
    pending_relations = []

    with transaction.atomic():
        for index, row in enumerate(rows, start=2):
            normalized = {str(key).strip(): (value or '').strip() for key, value in row.items() if key is not None}
            if not any(normalized.values()):
                continue

            person_data = _person_data_from_csv_row(normalized, index)
            person = Person.objects.create(**person_data)

            row_key = normalized.get('key')
            if row_key:
                if row_key in created_people_by_key:
                    raise ValueError(f'Row {index}: duplicate key "{row_key}".')
                created_people_by_key[row_key] = person

            pending_relations.append({
                'line': index,
                'person': person,
                'family_name': normalized.get('family_name', ''),
                'family_id': normalized.get('family_id', ''),
                'father_key': normalized.get('father_key', ''),
                'mother_key': normalized.get('mother_key', ''),
                'spouse_key': normalized.get('spouse_key', ''),
                'father_id': normalized.get('father_id', ''),
                'mother_id': normalized.get('mother_id', ''),
                'spouse_id': normalized.get('spouse_id', ''),
            })

        created_count = len(pending_relations)
        if not created_count:
            raise ValueError('CSV file only contained blank rows.')

        for relation_data in pending_relations:
            person = relation_data['person']
            family = _resolve_import_family_reference(
                family_name=relation_data['family_name'],
                family_id=relation_data['family_id'],
                line_number=relation_data['line'],
            )
            father = _resolve_import_person_reference(
                reference_key=relation_data['father_key'],
                reference_id=relation_data['father_id'],
                created_people_by_key=created_people_by_key,
                line_number=relation_data['line'],
                label='father',
            )
            mother = _resolve_import_person_reference(
                reference_key=relation_data['mother_key'],
                reference_id=relation_data['mother_id'],
                created_people_by_key=created_people_by_key,
                line_number=relation_data['line'],
                label='mother',
            )
            spouse = _resolve_import_person_reference(
                reference_key=relation_data['spouse_key'],
                reference_id=relation_data['spouse_id'],
                created_people_by_key=created_people_by_key,
                line_number=relation_data['line'],
                label='spouse',
            )

            person.family = family
            person.father = father
            person.mother = mother
            person.spouse = spouse
            person.save(update_fields=['family', 'father', 'mother', 'spouse'])

            if spouse and spouse.spouse_id != person.pk:
                spouse.spouse = person
                spouse.save(update_fields=['spouse'])

    return created_count


def _person_data_from_csv_row(row, line_number):
    first_name = row.get('first_name', '')
    last_name = row.get('last_name', '')
    if not first_name:
        raise ValueError(f'Row {line_number}: first_name is required.')

    gender = (row.get('gender') or 'O').upper()
    if gender not in {'M', 'F', 'O'}:
        raise ValueError(f'Row {line_number}: gender must be M, F, or O.')

    birth_date = _parse_optional_date(row.get('birth_date', ''), line_number, 'birth_date')
    death_date = _parse_optional_date(row.get('death_date', ''), line_number, 'death_date')
    if birth_date and death_date and death_date < birth_date:
        raise ValueError(f'Row {line_number}: death_date cannot be earlier than birth_date.')
    email = row.get('email', '')
    if email:
        try:
            validate_email(email)
        except Exception as exc:
            raise ValueError(f'Row {line_number}: email is not valid.') from exc

    return {
        'first_name': first_name,
        'last_name': last_name,
        'gender': gender,
        'birth_date': birth_date,
        'death_date': death_date,
        'birth_place': row.get('birth_place', ''),
        'email': email,
        'phone': row.get('phone', ''),
        'blood_group': row.get('blood_group', ''),
        'current_address': row.get('current_address', ''),
        'living_separately': _parse_optional_bool(row.get('living_separately', ''), line_number),
        'bio': row.get('bio', ''),
    }


def _resolve_import_family_reference(family_name, family_id, line_number):
    if family_id:
        try:
            return Family.objects.get(pk=int(family_id))
        except (Family.DoesNotExist, ValueError):
            raise ValueError(f'Row {line_number}: family_id "{family_id}" was not found.')
    if family_name:
        family = Family.objects.filter(name__iexact=family_name).first()
        if not family:
            raise ValueError(f'Row {line_number}: family_name "{family_name}" was not found.')
        return family
    return None


def _parse_optional_date(value, line_number, field_name):
    if not value:
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError(f'Row {line_number}: {field_name} must be in YYYY-MM-DD format.')
    return parsed


def _parse_optional_bool(value, line_number):
    if not value:
        return False
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'y'}:
        return True
    if normalized in {'0', 'false', 'no', 'n'}:
        return False
    raise ValueError(f'Row {line_number}: living_separately must be true/false, yes/no, or 1/0.')


def _resolve_import_person_reference(reference_key, reference_id, created_people_by_key, line_number, label):
    if reference_key:
        person = created_people_by_key.get(reference_key)
        if not person:
            raise ValueError(f'Row {line_number}: {label}_key "{reference_key}" was not found in the CSV.')
        return person
    if reference_id:
        try:
            return Person.objects.get(pk=int(reference_id))
        except (TypeError, ValueError):
            raise ValueError(f'Row {line_number}: {label}_id must be a numeric member ID.')
        except Person.DoesNotExist:
            raise ValueError(f'Row {line_number}: {label}_id "{reference_id}" does not exist.')
    return None
