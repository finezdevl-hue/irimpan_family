from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import migrations, models


def _normalize_name(name):
    replacements = {
        'Rev.Sr.': 'Rev. Sr.',
        'Rev. Fr.Seejo': 'Rev. Fr. Seejo',
        'Sr.Jolly': 'Sr. Jolly',
        'Sr.Thiyyama': 'Sr. Thiyyama',
        'Rv. Sr.': 'Rev. Sr.',
        'Geevarghese achan': 'Geevarghese Achan',
    }
    cleaned = name
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned.strip()


def load_clergy_members(apps, schema_editor):
    ClergyMember = apps.get_model('tree', 'ClergyMember')
    source_dir = Path(settings.BASE_DIR) / 'priest'
    if not source_dir.exists():
        return

    for image_path in sorted(source_dir.iterdir(), key=lambda path: path.name.lower()):
        if not image_path.is_file():
            continue
        name = _normalize_name(image_path.stem)
        if ClergyMember.objects.filter(name=name).exists():
            continue
        with image_path.open('rb') as source_file:
            member = ClergyMember(name=name)
            member.image.save(image_path.name, File(source_file), save=False)
            member.save()


def unload_clergy_members(apps, schema_editor):
    ClergyMember = apps.get_model('tree', 'ClergyMember')
    ClergyMember.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0019_alter_person_last_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClergyMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('image', models.ImageField(upload_to='priest/')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(load_clergy_members, unload_clergy_members),
    ]
