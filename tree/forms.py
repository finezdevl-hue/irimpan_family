from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Person, Event, GalleryPhoto


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
        if not (user.is_staff or user.is_superuser):
            raise forms.ValidationError(
                'Only admin accounts can sign in here.',
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
