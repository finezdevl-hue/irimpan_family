from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from .models import Person, Event, GalleryPhoto, SiteAd, LiveStreamSettings


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class EventChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.title} | {obj.event_date}"


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'gender', 'birth_date',
                  'death_date', 'birth_place', 'email', 'phone', 'blood_group',
                  'current_address', 'living_separately', 'bio', 'photo', 'father', 'mother', 'spouse']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last name'}),
            'gender': forms.Select(attrs={'class': 'form-input'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'death_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'birth_place': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City, Country'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email address'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone number'}),
            'blood_group': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'A+, O-, B+, etc.'}),
            'current_address': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Current address'}),
            'living_separately': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'bio': forms.Textarea(attrs={'class': 'form-input rich-text-input', 'rows': 8, 'placeholder': 'Short biography...'}),
            'father': forms.Select(attrs={'class': 'form-input'}),
            'mother': forms.Select(attrs={'class': 'form-input'}),
            'spouse': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'birth_date': 'Date of Birth',
            'death_date': 'Date of Death',
            'birth_place': 'Birth Place',
            'blood_group': 'Blood Group',
            'current_address': 'Current Address',
            'living_separately': 'Living Separately',
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        self.fields['father'].queryset = Person.objects.filter(gender='M')
        self.fields['mother'].queryset = Person.objects.filter(gender='F')
        if instance:
            self.fields['spouse'].queryset = Person.objects.exclude(pk=instance.pk)
        self.fields['father'].empty_label = '— Select Father —'
        self.fields['mother'].empty_label = '— Select Mother —'
        self.fields['spouse'].empty_label = '— Select Spouse —'
        for field in self.fields.values():
            field.required = False
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True


class MemberAccountForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=Person.objects.all(),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Family Member',
    )
    allow_dashboard_login = forms.BooleanField(
        required=False,
        label='Enable Member Login',
    )
    login_username = forms.CharField(
        required=False,
        max_length=150,
        label='Login Username',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Username for this member'}),
    )
    login_password = forms.CharField(
        required=False,
        label='Login Password',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Set or reset password'}),
        help_text='Required when creating a new member login. Leave blank to keep the existing password.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['member'].queryset = Person.objects.all().order_by('last_name', 'first_name')
        self.fields['member'].empty_label = 'Select a member'

    def clean_login_username(self):
        username = (self.cleaned_data.get('login_username') or '').strip()
        if not username:
            return ''

        User = get_user_model()
        selected_member = self.cleaned_data.get('member')
        existing_user = User.objects.filter(username__iexact=username).first()
        current_user = getattr(selected_member, 'user', None) if selected_member else None
        if existing_user and existing_user != current_user:
            linked_person = getattr(existing_user, 'family_member_profile', None)
            if linked_person and linked_person != selected_member:
                raise forms.ValidationError('This username is already linked to another family member.')
            if existing_user.is_staff or existing_user.is_superuser:
                raise forms.ValidationError('This username is already reserved for an admin account.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')
        allow_dashboard_login = cleaned_data.get('allow_dashboard_login')
        username = (cleaned_data.get('login_username') or '').strip()
        password = cleaned_data.get('login_password') or ''

        if allow_dashboard_login and not username:
            self.add_error('login_username', 'Enter a username to enable member login.')

        if allow_dashboard_login and member and not getattr(member, 'user', None) and not password:
            self.add_error('login_password', 'Enter a password for the new member login.')

        return cleaned_data

    def save(self):
        member = self.cleaned_data['member']
        save_member_login(
            person=member,
            allow_dashboard_login=self.cleaned_data.get('allow_dashboard_login'),
            username=self.cleaned_data.get('login_username'),
            password=self.cleaned_data.get('login_password'),
        )
        return member


def save_member_login(*, person, allow_dashboard_login, username, password):
    username = (username or '').strip()
    password = password or ''
    current_user = person.user

    if not allow_dashboard_login:
        if current_user:
            family_group, _ = Group.objects.get_or_create(name='family_member')
            current_user.groups.remove(family_group)
            current_user.is_active = False
            current_user.save(update_fields=['is_active'])
            person.user = None
            person.save(update_fields=['user'])
        return

    User = get_user_model()
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        user = current_user or User(username=username)

    user.username = username
    user.first_name = person.first_name
    user.last_name = person.last_name
    user.email = person.email
    user.is_active = True
    if password:
        user.set_password(password)
    elif user.pk is None:
        user.set_unusable_password()
    user.save()

    family_group, _ = Group.objects.get_or_create(name='family_member')
    user.groups.add(family_group)

    if person.user_id != user.pk:
        person.user = user
        person.save(update_fields=['user'])


class MemberCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-input', 'accept': '.csv,text/csv'}),
        help_text='Upload a CSV file with member details.',
    )

    def clean_csv_file(self):
        uploaded = self.cleaned_data['csv_file']
        name = (uploaded.name or '').lower()
        if not name.endswith('.csv'):
            raise forms.ValidationError('Please upload a CSV file.')
        return uploaded


class AdminLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Admin username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password'})
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_staff or user.is_superuser or user.groups.filter(name='family_member').exists()):
            raise forms.ValidationError(
                'Only admin and family member accounts can sign in here.',
                code='not_admin',
            )


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'tag', 'event_date', 'location', 'description', 'image']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Event title'}),
            'tag': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Annual Meet / Memorial / Gathering'}),
            'event_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Location'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 5, 'placeholder': 'Event description'}),
        }


class GalleryPhotoForm(forms.ModelForm):
    event = EventChoiceField(
        queryset=Event.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    images = forms.FileField(
        required=False,
        widget=MultiFileInput(attrs={'class': 'form-input', 'multiple': True}),
    )

    class Meta:
        model = GalleryPhoto
        fields = ['title', 'event', 'event_name', 'event_date', 'image', 'images', 'caption']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Photo title'}),
            'event_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Completed event name'}),
            'event_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'caption': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Short caption about this event photo'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].queryset = Event.objects.all().order_by('event_date', 'title')
        self.fields['event'].empty_label = 'Select Upcoming Event'
        self.fields['image'].required = False
        self.fields['images'].label = 'Multiple Images'
        self.fields['event_name'].required = False
        self.fields['event_date'].required = False
        self.fields['event_name'].widget.attrs['readonly'] = True
        self.fields['event_date'].widget.attrs['readonly'] = True


class SiteAdForm(forms.ModelForm):
    class Meta:
        model = SiteAd
        fields = [
            'title',
            'image',
            'button_text',
            'button_url',
            'display_type',
            'priority',
            'start_date',
            'end_date',
            'is_active',
            'show_as_popup',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ad title'}),
            'button_text': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Button text'}),
            'button_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://example.com'}),
            'display_type': forms.Select(attrs={'class': 'form-input'}),
            'priority': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'placeholder': '0'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_as_popup': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        labels = {
            'button_text': 'Button Text',
            'button_url': 'Button URL',
            'display_type': 'Display Type',
            'priority': 'Priority',
            'start_date': 'Date From',
            'end_date': 'Date To',
            'is_active': 'Ad Active',
            'show_as_popup': 'Popup Active',
        }

    def clean(self):
        cleaned_data = super().clean()
        button_text = (cleaned_data.get('button_text') or '').strip()
        button_url = (cleaned_data.get('button_url') or '').strip()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        display_type = cleaned_data.get('display_type')
        show_as_popup = cleaned_data.get('show_as_popup')

        if button_text and not button_url:
            self.add_error('button_url', 'Enter a button URL when button text is provided.')
        if button_url and not button_text:
            self.add_error('button_text', 'Enter button text when button URL is provided.')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'Date To cannot be earlier than Date From.')
        if display_type == SiteAd.DISPLAY_POPUP and not show_as_popup:
            self.add_error('show_as_popup', 'Popup ads need Popup Active enabled to appear on the homepage.')

        return cleaned_data

    def save(self, commit=True):
        ad = super().save(commit=False)
        ad.message = ''
        if commit:
            ad.save()
        return ad


class LiveStreamSettingsForm(forms.ModelForm):
    class Meta:
        model = LiveStreamSettings
        fields = ['title', 'youtube_url', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Live Stream Title'}),
            'youtube_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://www.youtube.com/watch?v=...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        labels = {
            'youtube_url': 'YouTube Live Link',
            'is_active': 'Live Stream Active',
        }

    def clean_youtube_url(self):
        url = (self.cleaned_data.get('youtube_url') or '').strip()
        if not url:
            return ''
        temp = LiveStreamSettings(youtube_url=url)
        if not temp.youtube_video_id:
            raise forms.ValidationError('Enter a valid YouTube watch, live, share, or embed link.')
        return url
