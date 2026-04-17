from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0022_family_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='family_photo',
            field=models.ImageField(upload_to='family_photos/', null=True, blank=True),
        ),
    ]
