from django.db import migrations


NAME_UPDATES = {
    'priest/Geevarghese_achan.jpg': 'Geevarghese Achan',
    'priest/Rv._Sr._Lissy_John.jpg': 'Rev. Sr. Lissy John',
}


def update_clergy_names(apps, schema_editor):
    ClergyMember = apps.get_model('tree', 'ClergyMember')
    for image_name, new_name in NAME_UPDATES.items():
        ClergyMember.objects.filter(image=image_name).update(name=new_name)


def reverse_clergy_names(apps, schema_editor):
    ClergyMember = apps.get_model('tree', 'ClergyMember')
    ClergyMember.objects.filter(image='priest/Geevarghese_achan.jpg').update(name='Geevarghese achan')
    ClergyMember.objects.filter(image='priest/Rv._Sr._Lissy_John.jpg').update(name='Rv. Sr. Lissy John')


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0020_clergymember'),
    ]

    operations = [
        migrations.RunPython(update_clergy_names, reverse_clergy_names),
    ]
