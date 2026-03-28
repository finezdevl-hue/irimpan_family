from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.core.validators import validate_email
from django.db import transaction
from django.utils.dateparse import parse_date
from .models import Person, Event, GalleryPhoto
from .forms import PersonForm, MemberCSVUploadForm, AdminLoginForm, EventForm, GalleryPhotoForm
import csv
import io
import json


admin_required = user_passes_test(
    lambda user: user.is_authenticated and (user.is_staff or user.is_superuser),
    login_url='admin_login',
)


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
    return render(request, 'tree/home.html', {
        'people': people,
        'total': total,
        'generations': generations,
        'mentors': mentors,
        'upcoming_events': upcoming_events,
    })


def about(request):
    stats = _site_stats()
    return render(request, 'tree/about.html', stats)


def family_page(request):
    people = list(Person.objects.all())
    generation_map = _generation_map(people)
    _apply_generations(people, generation_map)
    households = _build_households(people)
    return render(request, 'tree/family.html', {
        'people': people,
        'households': households,
        'total_families': len(households),
        'generations': max(generation_map.values(), default=0),
    })


def family_detail(request, guardian_pk):
    people = list(Person.objects.all())
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
    return render(request, 'tree/event_detail.html', {
        'event': event,
        'other_events': other_events,
    })


def gallery(request):
    gallery_items = GalleryPhoto.objects.all()
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
    return render(request, 'tree/contact.html')


def admin_login(request):
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
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
    people_count = Person.objects.count()
    event_count = Event.objects.count()
    gallery_count = GalleryPhoto.objects.count()
    recent_people = Person.objects.all()[:5]
    recent_events = Event.objects.all()[:5]
    recent_gallery = GalleryPhoto.objects.all()[:5]
    return render(request, 'tree/admin_dashboard.html', {
        'people_count': people_count,
        'event_count': event_count,
        'gallery_count': gallery_count,
        'recent_people': recent_people,
        'recent_events': recent_events,
        'recent_gallery': recent_gallery,
    })


@admin_required
def admin_members(request):
    people = Person.objects.all()
    return render(request, 'tree/admin_members.html', {'people': people})


@admin_required
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
    return render(request, 'tree/admin_member_form.html', {
        'form': form,
        'action': 'Add',
        'csv_upload_form': csv_upload_form,
        'csv_expected_headers': _csv_expected_headers(),
    })


@admin_required
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
    return render(request, 'tree/admin_member_form.html', {'form': form, 'action': 'Edit', 'person': person, 'csv_upload_form': MemberCSVUploadForm()})


@admin_required
def admin_member_delete(request, pk):
    person = get_object_or_404(Person, pk=pk)
    if request.method == 'POST':
        name = person.full_name
        person.delete()
        messages.success(request, f'{name} deleted successfully.')
        return redirect('admin_members')
    return render(request, 'tree/admin_member_delete.html', {'person': person})


@admin_required
def admin_events(request):
    events = Event.objects.all()
    return render(request, 'tree/admin_events.html', {'events': events})


@admin_required
def admin_gallery(request):
    gallery_items = GalleryPhoto.objects.all()
    return render(request, 'tree/admin_gallery.html', {'gallery_items': gallery_items})


@admin_required
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
    return render(request, 'tree/admin_gallery_form.html', {'form': form, 'action': 'Add'})


@admin_required
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
    return render(request, 'tree/admin_gallery_form.html', {'form': form, 'action': 'Edit', 'item': item})


@admin_required
def admin_gallery_delete(request, pk):
    item = get_object_or_404(GalleryPhoto, pk=pk)
    if request.method == 'POST':
        title = item.title
        item.delete()
        messages.success(request, f'{title} removed from the gallery.')
        return redirect('admin_gallery')
    return render(request, 'tree/admin_gallery_delete.html', {'item': item})


@admin_required
def admin_event_add(request):
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            messages.success(request, f'{event.title} added successfully.')
            return redirect('admin_events')
    else:
        form = EventForm()
    return render(request, 'tree/admin_event_form.html', {'form': form, 'action': 'Add'})


@admin_required
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
    return render(request, 'tree/admin_event_form.html', {'form': form, 'action': 'Edit', 'event': event})


@admin_required
def admin_event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        title = event.title
        event.delete()
        messages.success(request, f'{title} deleted successfully.')
        return redirect('admin_events')
    return render(request, 'tree/admin_event_delete.html', {'event': event})


def tree_view(request):
    people = Person.objects.all()
    return render(request, 'tree/tree.html', {'people': people})


def tree_data(request):
    people = list(Person.objects.all())
    _apply_generations(people, _generation_map(people))
    nodes = []
    edges = []

    for p in people:
        nodes.append(p.to_dict())
        if p.father_id:
            edges.append({'from': p.father_id, 'to': p.pk, 'type': 'parent'})
        if p.mother_id:
            edges.append({'from': p.mother_id, 'to': p.pk, 'type': 'parent'})
        if p.spouse_id and p.pk < p.spouse_id:
            edges.append({'from': p.pk, 'to': p.spouse_id, 'type': 'spouse'})

    return JsonResponse({'nodes': nodes, 'edges': edges})


def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    children = person.get_children()
    siblings = person.get_siblings()
    generation_map = _generation_map(Person.objects.all())
    _apply_generations([person, *children, *siblings], generation_map)
    if person.father:
        person.father._generation = generation_map.get(person.father_id, 1)
    if person.mother:
        person.mother._generation = generation_map.get(person.mother_id, 1)
    if person.spouse:
        person.spouse._generation = generation_map.get(person.spouse_id, 1)
    return render(request, 'tree/person_detail.html', {
        'person': person,
        'children': children,
        'siblings': siblings,
    })


@admin_required
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


@admin_required
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


@admin_required
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
        households.append({
            'guardian': guardian,
            'partner': partner,
            'members': members,
            'resident_count': len(members),
            'family_name': guardian.last_name or (partner.last_name if partner else 'Family'),
            'is_separate_home': guardian.living_separately,
            'house_key': guardian.pk,
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
    missing_headers = [header for header in ('first_name', 'last_name') if header not in received_headers]
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

            person.father = father
            person.mother = mother
            person.spouse = spouse
            person.save(update_fields=['father', 'mother', 'spouse'])

            if spouse and spouse.spouse_id != person.pk:
                spouse.spouse = person
                spouse.save(update_fields=['spouse'])

    return created_count


def _person_data_from_csv_row(row, line_number):
    first_name = row.get('first_name', '')
    last_name = row.get('last_name', '')
    if not first_name or not last_name:
        raise ValueError(f'Row {line_number}: first_name and last_name are required.')

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
