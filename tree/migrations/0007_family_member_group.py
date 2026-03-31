from django.db import migrations


def create_family_member_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    group, _ = Group.objects.get_or_create(name='family_member')
    permission_codenames = ['add_event', 'add_galleryphoto']
    permissions = Permission.objects.filter(codename__in=permission_codenames)
    group.permissions.set(permissions)


def remove_family_member_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='family_member').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0006_galleryphoto_event_alter_galleryphoto_image'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_family_member_group, remove_family_member_group),
    ]
