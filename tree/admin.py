from django.contrib import admin
from .models import Person, SiteAd, LiveStreamSettings

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'gender', 'birth_date', 'birth_place', 'is_alive']
    search_fields = ['first_name', 'last_name']
    list_filter = ['gender']


@admin.register(SiteAd)
class SiteAdAdmin(admin.ModelAdmin):
    list_display = ['title', 'display_type', 'priority', 'is_active', 'show_as_popup', 'start_date', 'end_date', 'created_at']
    search_fields = ['title', 'message']
    list_filter = ['display_type', 'is_active', 'show_as_popup']


@admin.register(LiveStreamSettings)
class LiveStreamSettingsAdmin(admin.ModelAdmin):
    list_display = ['title', 'youtube_url', 'is_active', 'updated_at']
    search_fields = ['title', 'youtube_url']
    list_filter = ['is_active']
