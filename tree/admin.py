from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from .models import (
    Person,
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


WHATSAPP_MESSAGE_RESET_KEY = 'whatsapp-message-reset-offset'

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'gender', 'birth_date', 'wedding_date', 'birth_place', 'is_alive']
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


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ['year', 'title', 'is_active', 'updated_at']
    search_fields = ['year', 'title', 'description']
    list_filter = ['is_active']


@admin.register(CommitteeMember)
class CommitteeMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'position', 'committee', 'sort_order', 'updated_at']
    search_fields = ['name', 'position', 'committee__year', 'committee__title']
    list_filter = ['committee']


@admin.register(MemberGroup)
class MemberGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'updated_at']
    search_fields = ['name', 'description']
    list_filter = ['is_active']


@admin.register(HeroImage)
class HeroImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'sort_order', 'is_active', 'updated_at']
    search_fields = ['title', 'alt_text']
    list_filter = ['is_active']


@admin.register(ClergyMember)
class ClergyMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'ordination_day']
    search_fields = ['name']


@admin.register(WhatsAppBroadcast)
class WhatsAppBroadcastAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'sent_count', 'failed_count', 'created_at']
    search_fields = ['title', 'message']
    list_filter = ['status']


@admin.register(WhatsAppBroadcastRecipient)
class WhatsAppBroadcastRecipientAdmin(admin.ModelAdmin):
    change_list_template = 'admin/tree/whatsappbroadcastrecipient/change_list.html'
    list_display = ['phone', 'status', 'broadcast', 'updated_at']
    search_fields = ['phone', 'error_message', 'broadcast__title']
    list_filter = ['status']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'reset-message-count/',
                self.admin_site.admin_view(self.reset_message_count_view),
                name='tree_whatsappbroadcastrecipient_reset_message_count',
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['reset_message_count_url'] = reverse(
            'admin:tree_whatsappbroadcastrecipient_reset_message_count'
        )
        return super().changelist_view(request, extra_context=extra_context)

    def reset_message_count_view(self, request):
        if request.method != 'POST':
            changelist_url = reverse('admin:tree_whatsappbroadcastrecipient_changelist')
            return HttpResponseRedirect(changelist_url)
        if not request.user.is_superuser:
            self.message_user(
                request,
                'Only the super admin can reset the message count.',
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse('admin:tree_whatsappbroadcastrecipient_changelist'))

        sent_count = WhatsAppBroadcastRecipient.objects.filter(
            status=WhatsAppBroadcastRecipient.STATUS_SENT
        ).count()
        SiteVisitCounter.objects.update_or_create(
            key=WHATSAPP_MESSAGE_RESET_KEY,
            defaults={'total_visits': sent_count},
        )
        self.message_user(request, 'Message count reset successfully.', level=messages.SUCCESS)
        return HttpResponseRedirect(reverse('admin:tree_whatsappbroadcastrecipient_changelist'))
