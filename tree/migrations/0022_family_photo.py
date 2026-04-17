from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0021_update_clergy_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='family',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='family/'),
        ),
    ]
