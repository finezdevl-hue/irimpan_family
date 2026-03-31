import os

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Person(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='O')
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    blood_group = models.CharField(max_length=10, blank=True)
    current_address = models.TextField(blank=True)
    living_separately = models.BooleanField(default=False)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='photos/', null=True, blank=True)
    father = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children_as_father'
    )
    mother = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children_as_mother'
    )
    spouse = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='married_to'
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='family_member_profile',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('person_detail', kwargs={'pk': self.pk})

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_alive(self):
        return self.death_date is None

    @property
    def age(self):
        if not self.birth_date:
            return None
        from datetime import date
        end = self.death_date or date.today()
        years = end.year - self.birth_date.year
        if (end.month, end.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    @property
    def generation(self):
        return getattr(self, '_generation', 1)

    def get_children(self):
        father_children = Person.objects.filter(father=self)
        mother_children = Person.objects.filter(mother=self)
        return (father_children | mother_children).distinct()

    def get_siblings(self):
        siblings = Person.objects.none()
        if self.father:
            siblings = siblings | Person.objects.filter(father=self.father).exclude(pk=self.pk)
        if self.mother:
            siblings = siblings | Person.objects.filter(mother=self.mother).exclude(pk=self.pk)
        return siblings.distinct()

    def to_dict(self):
        return {
            'id': self.pk,
            'name': self.full_name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'gender': self.gender,
            'birth_date': self.birth_date.strftime('%Y-%m-%d') if self.birth_date else None,
            'death_date': self.death_date.strftime('%Y-%m-%d') if self.death_date else None,
            'birth_place': self.birth_place,
            'email': self.email,
            'phone': self.phone,
            'blood_group': self.blood_group,
            'current_address': self.current_address,
            'living_separately': self.living_separately,
            'bio': self.bio,
            'photo': self.photo.url if self.photo else None,
            'father_id': self.father_id,
            'mother_id': self.mother_id,
            'spouse_id': self.spouse_id,
            'generation': self.generation,
            'age': self.age,
            'is_alive': self.is_alive,
            'url': self.get_absolute_url(),
        }


class Event(models.Model):
    title = models.CharField(max_length=200)
    tag = models.CharField(max_length=80, blank=True)
    event_date = models.DateField()
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to='events/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['event_date', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('event_detail', kwargs={'pk': self.pk})


def gallery_upload_to(instance, filename):
    event_title = instance.event.title if instance.event_id else instance.event_name or 'uncategorized-event'
    folder = slugify(event_title) or 'uncategorized-event'
    return os.path.join('gallery', folder, filename)


class GalleryPhoto(models.Model):
    title = models.CharField(max_length=200)
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL, related_name='gallery_photos')
    event_name = models.CharField(max_length=200)
    event_date = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to=gallery_upload_to)
    caption = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-created_at', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.event:
            self.event_name = self.event.title
            self.event_date = self.event.event_date
        super().save(*args, **kwargs)
