# Generated to add certificate type support for Original/Duplicate degree fees.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('degree', '0009_submitted_status_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='feestructure',
            name='certificate_type',
            field=models.CharField(choices=[('ORIGINAL', 'Original Degree'), ('DUPLICATE', 'Duplicate Degree')], default='ORIGINAL', max_length=20),
        ),
        migrations.AddField(
            model_name='degreeapplication',
            name='certificate_type',
            field=models.CharField(choices=[('ORIGINAL', 'Original Degree'), ('DUPLICATE', 'Duplicate Degree')], default='ORIGINAL', max_length=20),
        ),
        migrations.AlterModelOptions(
            name='feestructure',
            options={'ordering': ['program_level', 'certificate_type', 'timing', 'application_type', '-effective_from']},
        ),
        migrations.RemoveIndex(
            model_name='feestructure',
            name='degree_fees_program_e3b711_idx',
        ),
        migrations.AddIndex(
            model_name='feestructure',
            index=models.Index(fields=['program_level', 'certificate_type', 'application_type', 'timing', 'effective_from'], name='degree_fees_program_cer_idx'),
        ),
    ]
