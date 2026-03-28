#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

username = os.getenv("admin")
email = os.getenv("admin@gmail.com")
password = os.getenv("admin")

if not (username and email and password):
    print("Skipping superuser creation. Set DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and DJANGO_SUPERUSER_PASSWORD to enable it.")
    raise SystemExit(0)

User = get_user_model()
user, created = User.objects.get_or_create(
    username=username,
    defaults={
        "email": email,
        "is_staff": True,
        "is_superuser": True,
    },
)

changed = False
if user.email != email:
    user.email = email
    changed = True
if not user.is_staff:
    user.is_staff = True
    changed = True
if not user.is_superuser:
    user.is_superuser = True
    changed = True

if created:
    user.set_password(password)
    changed = True

if changed:
    user.save()

print("Superuser ready.")
PY
