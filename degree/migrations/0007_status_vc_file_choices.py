from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('degree', '0006_cnic_formatted_lengths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='degreeapplication',
            name='status',
            field=models.CharField(
                choices=[
                    ('DOCUMENTS_REQUIRED', 'Objection'),
                    ('PENDING_VERIFICATION', 'In Process'),
                    ('PRINTED_PENDING_SIGNATURE', 'Printed'),
                    ('VC_FILE', 'VC File'),
                    ('READY_FOR_COLLECTION', 'Ready for Collection'),
                    ('DELIVERED', 'Collected'),
                    ('CANCELLED', 'Cancelled'),
                ],
                default='DOCUMENTS_REQUIRED',
                max_length=35,
            ),
        ),
        migrations.AlterField(
            model_name='applicationstatuslog',
            name='from_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('DOCUMENTS_REQUIRED', 'Objection'),
                    ('PENDING_VERIFICATION', 'In Process'),
                    ('PRINTED_PENDING_SIGNATURE', 'Printed'),
                    ('VC_FILE', 'VC File'),
                    ('READY_FOR_COLLECTION', 'Ready for Collection'),
                    ('DELIVERED', 'Collected'),
                    ('CANCELLED', 'Cancelled'),
                ],
                max_length=35,
            ),
        ),
        migrations.AlterField(
            model_name='applicationstatuslog',
            name='to_status',
            field=models.CharField(
                choices=[
                    ('DOCUMENTS_REQUIRED', 'Objection'),
                    ('PENDING_VERIFICATION', 'In Process'),
                    ('PRINTED_PENDING_SIGNATURE', 'Printed'),
                    ('VC_FILE', 'VC File'),
                    ('READY_FOR_COLLECTION', 'Ready for Collection'),
                    ('DELIVERED', 'Collected'),
                    ('CANCELLED', 'Cancelled'),
                ],
                max_length=35,
            ),
        ),
    ]
