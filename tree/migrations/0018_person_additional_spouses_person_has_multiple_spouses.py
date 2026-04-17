from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0017_family_person_family'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='additional_spouses',
            field=models.ManyToManyField(blank=True, to='tree.person'),
        ),
        migrations.AddField(
            model_name='person',
            name='has_multiple_spouses',
            field=models.BooleanField(default=False),
        ),
    ]
