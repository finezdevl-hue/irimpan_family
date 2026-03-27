from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from .models import Person, Event, GalleryPhoto
from .forms import PersonForm, AdminLoginForm, EventForm, GalleryPhotoForm
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
        return redirect('/admin/')

    form = AdminLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, 'Admin login successful.')
        return redirect('/admin/')
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
        form = PersonForm(request.POST, request.FILES)
        if form.is_valid():
            person = form.save()
            messages.success(request, f'{person.full_name} added successfully.')
            return redirect('admin_members')
    else:
        form = PersonForm()
    return render(request, 'tree/admin_member_form.html', {'form': form, 'action': 'Add'})


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
    return render(request, 'tree/admin_member_form.html', {'form': form, 'action': 'Edit', 'person': person})


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
