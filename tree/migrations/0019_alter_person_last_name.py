from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0018_person_additional_spouses_person_has_multiple_spouses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='last_name',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
