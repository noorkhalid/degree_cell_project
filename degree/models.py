from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max, Sum
from django.utils import timezone
from academics.models import Bank, Institute, Program


class ApplicationType(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    URGENT = 'URGENT', 'Urgent'


class FeeTiming(models.TextChoices):
    BEFORE_TIME = 'BEFORE_TIME', 'Before Time'
    AFTER_TIME = 'AFTER_TIME', 'After Time'


class ApplicationStatus(models.TextChoices):
    # Operational status names requested by the Degree Cell.
    # Existing database codes are kept where possible to avoid breaking old records.
    DOCUMENTS_REQUIRED = 'DOCUMENTS_REQUIRED', 'Objection'
    PENDING_VERIFICATION = 'PENDING_VERIFICATION', 'In Process'
    PRINTED_PENDING_SIGNATURE = 'PRINTED_PENDING_SIGNATURE', 'Printed'
    VC_FILE = 'VC_FILE', 'VC File'
    READY_FOR_COLLECTION = 'READY_FOR_COLLECTION', 'Ready for Collection'
    DELIVERED = 'DELIVERED', 'Collected'
    CANCELLED = 'CANCELLED', 'Cancelled'


ACTIVE_APPLICATION_STATUS_CHOICES = (
    (ApplicationStatus.DOCUMENTS_REQUIRED, ApplicationStatus.DOCUMENTS_REQUIRED.label),
    (ApplicationStatus.PENDING_VERIFICATION, ApplicationStatus.PENDING_VERIFICATION.label),
    (ApplicationStatus.PRINTED_PENDING_SIGNATURE, ApplicationStatus.PRINTED_PENDING_SIGNATURE.label),
    (ApplicationStatus.VC_FILE, ApplicationStatus.VC_FILE.label),
    (ApplicationStatus.READY_FOR_COLLECTION, ApplicationStatus.READY_FOR_COLLECTION.label),
)

APPLICATION_FILTER_STATUS_CHOICES = (
    (ApplicationStatus.DOCUMENTS_REQUIRED, ApplicationStatus.DOCUMENTS_REQUIRED.label),
    (ApplicationStatus.PENDING_VERIFICATION, ApplicationStatus.PENDING_VERIFICATION.label),
    (ApplicationStatus.PRINTED_PENDING_SIGNATURE, ApplicationStatus.PRINTED_PENDING_SIGNATURE.label),
    (ApplicationStatus.VC_FILE, ApplicationStatus.VC_FILE.label),
    (ApplicationStatus.READY_FOR_COLLECTION, ApplicationStatus.READY_FOR_COLLECTION.label),
    (ApplicationStatus.DELIVERED, ApplicationStatus.DELIVERED.label),
    (ApplicationStatus.CANCELLED, ApplicationStatus.CANCELLED.label),
)


LEGACY_STATUS_MAP = {
    'RECEIVED': ApplicationStatus.PENDING_VERIFICATION,
    'VERIFIED': ApplicationStatus.PENDING_VERIFICATION,
    'SENT_FOR_PRINTING': ApplicationStatus.PENDING_VERIFICATION,
    'RECEIVED_FOR_PRINT': ApplicationStatus.PENDING_VERIFICATION,
    'PRINTED': ApplicationStatus.PRINTED_PENDING_SIGNATURE,
    'SUBMITTED_FOR_APPROVAL': ApplicationStatus.VC_FILE,
}


class ReceivingMode(models.TextChoices):
    SELF = 'SELF', 'Self'
    REPRESENTATIVE = 'REPRESENTATIVE', 'Representative'
    COURIER = 'COURIER', 'Courier'


class FeeStructure(models.Model):
    program_level = models.CharField(max_length=20, choices=Program.Level.choices)
    application_type = models.CharField(max_length=20, choices=ApplicationType.choices)
    timing = models.CharField(max_length=20, choices=FeeTiming.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField(default=timezone.localdate, help_text='Date from which this fee becomes applicable.')
    effective_to = models.DateField(null=True, blank=True, help_text='Automatically filled when a newer fee replaces this one.')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_fee_structures')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['program_level', 'timing', 'application_type', '-effective_from']
        indexes = [
            models.Index(fields=['program_level', 'application_type', 'timing', 'effective_from']),
        ]

    def __str__(self):
        return f'{self.program_level} {self.application_type} {self.timing}: {self.amount} from {self.effective_from}'

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.is_active and self.effective_from <= today and (self.effective_to is None or self.effective_to >= today)

    @property
    def is_future(self):
        return self.is_active and self.effective_from > timezone.localdate()

    @property
    def is_expired(self):
        today = timezone.localdate()
        return (not self.is_active) or (self.effective_to is not None and self.effective_to < today)

    def clean(self):
        if self.timing == FeeTiming.BEFORE_TIME:
            self.application_type = ApplicationType.URGENT
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({'effective_to': 'Effective to date cannot be earlier than effective from date.'})

        overlap_qs = FeeStructure.objects.filter(
            program_level=self.program_level,
            application_type=self.application_type,
            timing=self.timing,
            is_active=True,
        ).exclude(pk=self.pk)
        for other in overlap_qs:
            other_to = other.effective_to or date.max
            self_to = self.effective_to or date.max
            if self.effective_from <= other_to and other.effective_from <= self_to:
                raise ValidationError(
                    'This fee period overlaps an existing active fee. Use the Replace Current Fee option or choose a later effective date.'
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def replace_current(cls, *, program_level, application_type, timing, amount, effective_from, created_by=None, remarks=''):
        if timing == FeeTiming.BEFORE_TIME:
            application_type = ApplicationType.URGENT
        with transaction.atomic():
            previous_fees = cls.objects.select_for_update().filter(
                program_level=program_level,
                application_type=application_type,
                timing=timing,
                is_active=True,
                effective_from__lt=effective_from,
            ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=effective_from))
            for previous in previous_fees:
                previous.effective_to = effective_from - timedelta(days=1)
                previous.save(update_fields=['effective_to', 'updated_at'])
            return cls.objects.create(
                program_level=program_level,
                application_type=application_type,
                timing=timing,
                amount=amount,
                effective_from=effective_from,
                effective_to=None,
                is_active=True,
                created_by=created_by,
                remarks=remarks,
            )

    @classmethod
    def get_applicable(cls, program_level, application_type, timing, on_date=None):
        on_date = on_date or timezone.localdate()
        return cls.objects.filter(
            program_level=program_level,
            application_type=application_type,
            timing=timing,
            is_active=True,
            effective_from__lte=on_date,
        ).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date)
        ).order_by('-effective_from').first()


class DegreeApplication(models.Model):
    tracking_no = models.CharField(max_length=20, unique=True, editable=False)
    status = models.CharField(max_length=35, choices=ApplicationStatus.choices, default=ApplicationStatus.DOCUMENTS_REQUIRED)

    student_name = models.CharField(max_length=255)
    father_name = models.CharField(max_length=255)
    cnic = models.CharField(max_length=25, db_index=True, help_text='Digits only are stored; forms may show dashes')
    mobile = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default='')
    postal_address = models.TextField()

    registration_no = models.CharField(max_length=100, db_index=True)
    roll_no = models.CharField(max_length=100, blank=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    institute = models.ForeignKey(Institute, on_delete=models.PROTECT)
    session_year = models.CharField(max_length=50, blank=True)
    exam_passing_year = models.CharField(max_length=20, blank=True)
    declared_result_date = models.DateField(default=timezone.localdate)
    verified_result_date = models.DateField(null=True, blank=True)

    application_type = models.CharField(max_length=20, choices=ApplicationType.choices)
    fee_structure_at_entry = models.ForeignKey(FeeStructure, null=True, blank=True, on_delete=models.PROTECT, related_name='applications')
    fee_timing_at_entry = models.CharField(max_length=20, choices=FeeTiming.choices)
    required_fee_at_entry = models.DecimalField(max_digits=10, decimal_places=2)
    final_fee_timing = models.CharField(max_length=20, choices=FeeTiming.choices, blank=True)
    final_required_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    received_mode = models.CharField(max_length=20, choices=ReceivingMode.choices, default=ReceivingMode.SELF)
    receiver_name = models.CharField(max_length=255, blank=True)
    receiver_cnic = models.CharField(max_length=25, blank=True)
    receiver_mobile = models.CharField(max_length=20, blank=True)
    receiving_remarks = models.CharField(max_length=255, blank=True)

    degree_serial_no = models.CharField(max_length=100, blank=True, unique=True, null=True)
    degree_book_no = models.CharField(max_length=100, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    printed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='printed_degrees')

    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_to_name = models.CharField(max_length=255, blank=True)
    delivered_to_cnic = models.CharField(max_length=25, blank=True)
    delivered_to_mobile = models.CharField(max_length=20, blank=True)
    delivery_mode = models.CharField(max_length=20, choices=ReceivingMode.choices, blank=True)
    courier_company = models.CharField(max_length=120, blank=True)
    courier_tracking_no = models.CharField(max_length=120, blank=True)
    courier_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_degree_applications')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tracking_no} - {self.student_name}'

    @staticmethod
    def calculate_timing(result_date, reference_date=None):
        reference_date = reference_date or timezone.localdate()
        delta_days = (reference_date - result_date).days
        return FeeTiming.BEFORE_TIME if delta_days <= 60 else FeeTiming.AFTER_TIME

    @staticmethod
    def get_required_fee(program_level, application_type, timing, on_date=None, return_fee=False):
        fee = FeeStructure.get_applicable(program_level, application_type, timing, on_date=on_date)
        if not fee:
            raise ValidationError('No fee structure found for selected level, type, timing, and application date.')
        return fee if return_fee else fee.amount

    @property
    def total_paid(self):
        return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    def generate_tracking_no(self):
        year = timezone.localdate().year
        prefix = f'DC-{str(year)[-2:]}-'
        with transaction.atomic():
            last = DegreeApplication.objects.select_for_update().filter(tracking_no__startswith=prefix).aggregate(max_no=Max('tracking_no'))['max_no']
            next_no = 1
            if last:
                next_no = int(last.split('-')[-1]) + 1
            return f'{prefix}{next_no:04d}'

    @staticmethod
    def normalize_cnic_value(value):
        return ''.join(ch for ch in str(value or '') if ch.isdigit())

    @staticmethod
    def normalize_mobile_value(value):
        return ''.join(ch for ch in str(value or '') if ch.isdigit())

    def clean(self):
        self.cnic = self.normalize_cnic_value(self.cnic)
        self.receiver_cnic = self.normalize_cnic_value(self.receiver_cnic)
        self.delivered_to_cnic = self.normalize_cnic_value(self.delivered_to_cnic)
        self.mobile = self.normalize_mobile_value(self.mobile)
        self.receiver_mobile = self.normalize_mobile_value(self.receiver_mobile)
        self.delivered_to_mobile = self.normalize_mobile_value(self.delivered_to_mobile)
        if self.cnic and len(self.cnic) != 13:
            raise ValidationError({'cnic': 'CNIC/Form-B must be 13 digits.'})
        if self.receiver_cnic and len(self.receiver_cnic) != 13:
            raise ValidationError({'receiver_cnic': 'Receiver CNIC must be 13 digits.'})
        if self.delivered_to_cnic and len(self.delivered_to_cnic) != 13:
            raise ValidationError({'delivered_to_cnic': 'Representative CNIC must be 13 digits.'})
        if self.mobile and len(self.mobile) != 11:
            raise ValidationError({'mobile': 'Mobile no must be 11 digits.'})
        if self.receiver_mobile and len(self.receiver_mobile) != 11:
            raise ValidationError({'receiver_mobile': 'Receiver mobile no must be 11 digits.'})
        if self.delivered_to_mobile and len(self.delivered_to_mobile) != 11:
            raise ValidationError({'delivered_to_mobile': 'Representative mobile no must be 11 digits.'})
        if self.degree_serial_no:
            qs = DegreeApplication.objects.filter(degree_serial_no=self.degree_serial_no).exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'degree_serial_no': 'Degree serial number already exists.'})

    def save(self, *args, **kwargs):
        if not self.tracking_no:
            self.tracking_no = self.generate_tracking_no()
        super().save(*args, **kwargs)


class ApplicationChecklist(models.Model):
    application = models.OneToOneField(DegreeApplication, on_delete=models.CASCADE, related_name='checklist')
    form_completely_filled = models.BooleanField(default=False)
    form_signed = models.BooleanField(default=False)
    attestations_complete = models.BooleanField(default=False)
    paid_challan_attached = models.BooleanField(default=False)
    original_clearance_attached = models.BooleanField(default=False)
    transcript_dmc_copy_attached = models.BooleanField(default=False)
    cnic_copy_attached = models.BooleanField(default=False)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    checked_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_complete(self):
        return all([
            self.form_completely_filled,
            self.form_signed,
            self.attestations_complete,
            self.paid_challan_attached,
            self.original_clearance_attached,
            self.transcript_dmc_copy_attached,
            self.cnic_copy_attached,
        ])

    @property
    def missing_documents(self):
        labels = {
            'form_completely_filled': 'Application Form',
            'form_signed': 'Application Form Signed',
            'attestations_complete': 'Required Attestations',
            'paid_challan_attached': 'Paid Bank Challan',
            'original_clearance_attached': 'Original Clearance Certificate',
            'transcript_dmc_copy_attached': 'Transcript / DMC Copy',
            'cnic_copy_attached': 'CNIC Copy',
        }
        return [label for field, label in labels.items() if not getattr(self, field)]

    def clean(self):
        # Incomplete checklists are allowed. Such applications remain in
        # DOCUMENTS_REQUIRED status and cannot move forward until completed.
        return None


class ApplicationPayment(models.Model):
    class PaymentType(models.TextChoices):
        INITIAL = 'INITIAL', 'Initial Fee'
        ADDITIONAL = 'ADDITIONAL', 'Additional Fee'

    application = models.ForeignKey(DegreeApplication, on_delete=models.CASCADE, related_name='payments')
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT)
    challan_no = models.CharField(max_length=100)
    challan_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.INITIAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('bank', 'challan_no')
        ordering = ['-challan_date']


class ApplicationStatusLog(models.Model):
    application = models.ForeignKey(DegreeApplication, on_delete=models.CASCADE, related_name='status_logs')
    from_status = models.CharField(max_length=35, choices=ApplicationStatus.choices, blank=True)
    to_status = models.CharField(max_length=35, choices=ApplicationStatus.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class VCFile(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted for Approval'
        RETURNED = 'RETURNED', 'Received / Ready for Collection'

    file_no = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_vc_files')
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.file_no

    @staticmethod
    def generate_file_no():
        """Generate yearly VC file numbers as 001/YYYY, 002/YYYY, ...

        The sequence restarts automatically at the beginning of every year because
        only file numbers ending with the current year are considered.
        """
        year = timezone.localdate().year
        suffix = f'/{year}'
        with transaction.atomic():
            existing_numbers = []
            for file_no in VCFile.objects.select_for_update().filter(file_no__endswith=suffix).values_list('file_no', flat=True):
                try:
                    number_part = str(file_no).split('/')[0].strip()
                    existing_numbers.append(int(number_part))
                except (TypeError, ValueError, IndexError):
                    continue
            next_number = (max(existing_numbers) if existing_numbers else 0) + 1
            return f'{next_number:03d}/{year}'

    def save(self, *args, **kwargs):
        if not self.file_no:
            self.file_no = self.generate_file_no()
        super().save(*args, **kwargs)


class VCFileItem(models.Model):
    vc_file = models.ForeignKey(VCFile, on_delete=models.CASCADE, related_name='items')
    application = models.OneToOneField(DegreeApplication, on_delete=models.PROTECT, related_name='vc_file_item')
    serial_no = models.PositiveIntegerField()

    class Meta:
        ordering = ['serial_no']
        unique_together = ('vc_file', 'serial_no')
