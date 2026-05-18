from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('degree', '0005_alter_degreeapplication_declared_result_date_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='degreeapplication',
            name='cnic',
            field=models.CharField(db_index=True, help_text='Digits only are stored; forms may show dashes', max_length=25),
        ),
        migrations.AlterField(
            model_name='degreeapplication',
            name='receiver_cnic',
            field=models.CharField(blank=True, max_length=25),
        ),
        migrations.AlterField(
            model_name='degreeapplication',
            name='delivered_to_cnic',
            field=models.CharField(blank=True, max_length=25),
        ),
    ]
