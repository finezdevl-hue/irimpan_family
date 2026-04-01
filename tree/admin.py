from django.contrib import admin
from .models import Person, SiteAd

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'gender', 'birth_date', 'birth_place', 'is_alive']
    search_fields = ['first_name', 'last_name']
    list_filter = ['gender']


@admin.register(SiteAd)
class SiteAdAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'show_as_popup', 'start_date', 'end_date', 'created_at']
    search_fields = ['title', 'message']
    list_filter = ['is_active', 'show_as_popup']
