"""
Management command to send WhatsApp birthday and death anniversary reminders.

Sends reminders 7 days before AND 1 day before the event.

Usage:
    python manage.py send_birthday_reminders
    python manage.py send_birthday_reminders --dry-run

Cron (run daily at 8 AM):
    0 8 * * * /path/to/venv/bin/python /path/to/manage.py send_birthday_reminders
"""

import json
import os
from datetime import date, timedelta
from urllib import request as urlrequest, error as urlerror

from django.core.management.base import BaseCommand

from tree.models import Person


def _send_whatsapp_cloud_message(phone, message_body):
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    api_version = os.getenv('WHATSAPP_API_VERSION', 'v23.0').strip() or 'v23.0'

    if not access_token or not phone_number_id:
        raise RuntimeError(
            'WhatsApp Cloud API is not configured. '
            'Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID env vars.'
        )

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
    with urlrequest.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode('utf-8') or '{}')


def _normalize_phone(phone: str) -> str | None:
    """Normalize phone to E.164 format, defaulting to +91 (India) if no country code."""
    digits = ''.join(c for c in phone if c.isdigit())
    if not digits:
        return None
    if phone.strip().startswith('+'):
        return '+' + digits
    # Default country code: India (+91)
    if len(digits) == 10:
        return '+91' + digits
    if len(digits) > 10:
        return '+' + digits
    return None


def _get_all_phone_numbers():
    """Return a mapping of person -> list of phones to notify.

    For each person with a birthday/deathday, we notify:
      - The person themselves (if alive and has a phone)
      - All other family members who have a phone
    """
    all_persons = list(
        Person.objects.filter(phone__isnull=False)
        .exclude(phone='')
        .select_related('family')
    )
    return all_persons


class Command(BaseCommand):
    help = 'Send WhatsApp birthday and death anniversary reminders (7-day and 1-day advance)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print messages without actually sending them',
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Override today\'s date (YYYY-MM-DD) for testing',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today_str = options.get('date')

        if today_str:
            today = date.fromisoformat(today_str)
        else:
            today = date.today()

        reminder_offsets = {7: '7 days', 1: '1 day'}
        sent = 0
        failed = 0
        skipped = 0

        for days_ahead, label in reminder_offsets.items():
            target_date = today + timedelta(days=days_ahead)

            # --- Birthday reminders ---
            birthday_persons = Person.objects.filter(
                birth_date__month=target_date.month,
                birth_date__day=target_date.day,
            ).exclude(birth_date__isnull=True)

            for person in birthday_persons:
                # Build age string
                turning_age = target_date.year - person.birth_date.year
                age_str = f' (turning {turning_age})' if turning_age > 0 else ''

                if days_ahead == 1:
                    msg = (
                        f"🎂 *Birthday Reminder – Tomorrow!*\n\n"
                        f"*{person.first_name} {person.last_name}*{age_str} "
                        f"has a birthday tomorrow, {target_date.strftime('%B %d')}. 🎉\n\n"
                        f"Don't forget to wish them!"
                    )
                else:
                    msg = (
                        f"🎂 *Birthday Reminder – {label} to go!*\n\n"
                        f"*{person.first_name} {person.last_name}*{age_str} "
                        f"has a birthday on {target_date.strftime('%B %d')} ({label} from now). 🎉\n\n"
                        f"Mark your calendar!"
                    )

                # Send to all family members who have a phone
                recipients = list(
                    Person.objects.filter(phone__isnull=False)
                    .exclude(phone='')
                    .values_list('phone', flat=True)
                    .distinct()
                )

                if not recipients:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No phone numbers found to notify about {person.first_name}\'s birthday.'
                        )
                    )
                    skipped += 1
                    continue

                self.stdout.write(
                    f'\n[BIRTHDAY – {label}] {person.first_name} {person.last_name} '
                    f'on {target_date} → notifying {len(recipients)} recipient(s)'
                )

                for raw_phone in recipients:
                    phone = _normalize_phone(raw_phone)
                    if not phone:
                        self.stdout.write(self.style.WARNING(f'  Skipping invalid phone: {raw_phone}'))
                        skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(f'  [DRY RUN] Would send to {phone}:\n  {msg}\n')
                        sent += 1
                    else:
                        try:
                            _send_whatsapp_cloud_message(phone, msg)
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Sent to {phone}'))
                            sent += 1
                        except Exception as exc:
                            self.stdout.write(self.style.ERROR(f'  ✗ Failed {phone}: {exc}'))
                            failed += 1

            # --- Death anniversary reminders ---
            death_persons = Person.objects.filter(
                death_date__month=target_date.month,
                death_date__day=target_date.day,
            ).exclude(death_date__isnull=True)

            for person in death_persons:
                years_ago = target_date.year - person.death_date.year
                years_str = f' ({years_ago}{"st" if years_ago == 1 else "nd" if years_ago == 2 else "rd" if years_ago == 3 else "th"} anniversary)' if years_ago > 0 else ''

                if days_ahead == 1:
                    msg = (
                        f"🕯️ *Death Anniversary Reminder – Tomorrow*\n\n"
                        f"Tomorrow, {target_date.strftime('%B %d')}, is the death anniversary of "
                        f"*{person.first_name} {person.last_name}*{years_str}. 🙏\n\n"
                        f"Let us remember them in our prayers."
                    )
                else:
                    msg = (
                        f"🕯️ *Death Anniversary Reminder – {label} to go*\n\n"
                        f"In {label}, on {target_date.strftime('%B %d')}, is the death anniversary of "
                        f"*{person.first_name} {person.last_name}*{years_str}. 🙏\n\n"
                        f"Let us remember them in our prayers."
                    )

                recipients = list(
                    Person.objects.filter(phone__isnull=False)
                    .exclude(phone='')
                    .values_list('phone', flat=True)
                    .distinct()
                )

                if not recipients:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No phone numbers found to notify about {person.first_name}\'s death anniversary.'
                        )
                    )
                    skipped += 1
                    continue

                self.stdout.write(
                    f'\n[DEATH ANNIVERSARY – {label}] {person.first_name} {person.last_name} '
                    f'on {target_date} → notifying {len(recipients)} recipient(s)'
                )

                for raw_phone in recipients:
                    phone = _normalize_phone(raw_phone)
                    if not phone:
                        self.stdout.write(self.style.WARNING(f'  Skipping invalid phone: {raw_phone}'))
                        skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(f'  [DRY RUN] Would send to {phone}:\n  {msg}\n')
                        sent += 1
                    else:
                        try:
                            _send_whatsapp_cloud_message(phone, msg)
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Sent to {phone}'))
                            sent += 1
                        except Exception as exc:
                            self.stdout.write(self.style.ERROR(f'  ✗ Failed {phone}: {exc}'))
                            failed += 1

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(
            self.style.SUCCESS(f'Done. Sent: {sent}  Failed: {failed}  Skipped: {skipped}')
        )
