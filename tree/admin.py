from django.contrib import admin
from .models import Person

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'gender', 'birth_date', 'birth_place', 'is_alive']
    search_fields = ['first_name', 'last_name']
    list_filter = ['gender']
