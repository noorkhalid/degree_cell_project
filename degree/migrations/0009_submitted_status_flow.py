# Generated to add Submitted status and update Degree Cell workflow.
from django.db import migrations, models


STATUS_CHOICES = [
    ('SUBMITTED', 'Submitted'),
    ('DOCUMENTS_REQUIRED', 'Objection'),
    ('PENDING_VERIFICATION', 'In Process'),
    ('PRINTED_PENDING_SIGNATURE', 'Printed'),
    ('VC_FILE', 'VC File'),
    ('READY_FOR_COLLECTION', 'Ready for Collection'),
    ('DELIVERED', 'Collected'),
    ('CANCELLED', 'Cancelled'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('degree', '0008_remove_degreeapplication_institute_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='degreeapplication',
            name='status',
            field=models.CharField(choices=STATUS_CHOICES, default='SUBMITTED', max_length=35),
        ),
        migrations.AlterField(
            model_name='applicationstatuslog',
            name='from_status',
            field=models.CharField(blank=True, choices=STATUS_CHOICES, max_length=35),
        ),
        migrations.AlterField(
            model_name='applicationstatuslog',
            name='to_status',
            field=models.CharField(choices=STATUS_CHOICES, max_length=35),
        ),
    ]
