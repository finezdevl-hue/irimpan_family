from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0023_person_family_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='clergymember',
            name='ordination_day',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='person',
            name='wedding_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
