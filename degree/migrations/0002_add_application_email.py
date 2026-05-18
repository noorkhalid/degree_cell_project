from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('degree', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='degreeapplication',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
    ]
