from decimal import Decimal
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from academics.models import Bank, Institute, Program, CourierCompany
from .models import (
    ApplicationChecklist,
    ApplicationPayment,
    ACTIVE_APPLICATION_STATUS_CHOICES,
    ApplicationStatus,
    ApplicationType,
    DegreeApplication,
    FeeStructure,
    FeeTiming,
    ReceivingMode,
    VCFile,
)


def normalize_cnic(value):
    """Return only CNIC digits so spaces/dashes are never counted."""
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def normalize_mobile(value):
    """Return only mobile digits so the dash shown in forms is never stored."""
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


class ChecklistGateForm(forms.Form):
    form_completely_filled = forms.BooleanField(required=False, label='Application Form')
    form_signed = forms.BooleanField(required=False, label='Application Form Signed')
    attestations_complete = forms.BooleanField(required=False, label='Required Attestations')
    paid_challan_attached = forms.BooleanField(required=False, label='Paid Bank Challan')
    original_clearance_attached = forms.BooleanField(required=False, label='Original Clearance Certificate')
    transcript_dmc_copy_attached = forms.BooleanField(required=False, label='Transcript / DMC Copy')
    cnic_copy_attached = forms.BooleanField(required=False, label='CNIC Copy')



class DegreeApplicationForm(forms.ModelForm):
    # Frontend accepts formatted CNIC like 17301-8021688-3 (15 chars).
    # clean_cnic() below strips dashes so the database still stores 13 digits only.
    cnic = forms.CharField(max_length=25, required=True, label='CNIC no')
    bank = forms.ModelChoiceField(queryset=Bank.objects.filter(is_active=True), required=True, empty_label='Select Bank')
    challan_no = forms.CharField(max_length=100, required=True)
    challan_date = forms.DateField(
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                                'class': 'date-picker-input',
            },
        ),
        required=True,
        label='Challan date',
    )
    timing = forms.ChoiceField(choices=[('', 'Select Timing')] + list(FeeTiming.choices), required=True, label='Timing')
    challan_amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False, disabled=True,
                                        help_text='Calculated automatically from the active fee schedule.')

    class Meta:
        model = DegreeApplication
        fields = [
            'student_name', 'father_name', 'cnic', 'mobile', 'email', 'registration_no', 'roll_no',
            'postal_address', 'program', 'institute', 'application_type', 'received_mode',
        ]
        widgets = {
            'postal_address': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'student_name': 'Name',
            'cnic': 'CNIC no',
            'roll_no': 'Roll No',
            'mobile': 'Mobile no',
            'email': 'Email address',
            'received_mode': 'Received mode',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.checklist_data = kwargs.pop('checklist_data', None) or {}
        super().__init__(*args, **kwargs)
        self.fields['program'].queryset = Program.objects.filter(is_active=True)
        self.fields['program'].empty_label = 'Select Program'
        self.fields['institute'].queryset = Institute.objects.filter(is_active=True)
        self.fields['institute'].empty_label = 'Select Institute'
        self.fields['bank'].empty_label = 'Select Bank'
        self.fields['timing'].choices = [('', 'Select Timing')] + list(FeeTiming.choices)
        self.fields['application_type'].choices = [('', 'Select Application Type')] + list(ApplicationType.choices)
        self.fields['received_mode'].choices = [('', 'Select Received Mode')] + list(ReceivingMode.choices)
        self.fields['challan_amount'].widget.attrs.update({'readonly': 'readonly', 'class': 'calculated-fee-input'})
        self.fields['email'].required = False
        self.fields['email'].widget.attrs.update({'placeholder': ''})
        self.fields['roll_no'].required = False
        self.fields['roll_no'].widget.attrs.update({'placeholder': ''})
        self.fields['cnic'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'cnic-input', 'placeholder': '00000-0000000-0'})
        self.fields['mobile'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'mobile-input', 'placeholder': ''})
        # Keep field order exactly as requested.
        requested_order = [
            'student_name', 'father_name', 'cnic', 'mobile', 'email', 'registration_no', 'roll_no',
            'postal_address', 'program', 'institute', 'timing', 'application_type',
            'bank', 'challan_no', 'challan_date', 'challan_amount', 'received_mode',
        ]
        self.order_fields(requested_order)

    def clean_cnic(self):
        value = normalize_cnic(self.cleaned_data.get('cnic'))
        if len(value) != 13:
            raise ValidationError('CNIC/Form-B must be 13 digits.')
        return value

    def clean_mobile(self):
        value = normalize_mobile(self.cleaned_data.get('mobile'))
        if len(value) != 11:
            raise ValidationError('Mobile no must be 11 digits.')
        return value

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get('program')
        timing = cleaned.get('timing')
        application_type = cleaned.get('application_type')

        # Business rule: a Before Time application is always Urgent.
        if timing == FeeTiming.BEFORE_TIME:
            application_type = ApplicationType.URGENT
            cleaned['application_type'] = ApplicationType.URGENT

        if program and timing and application_type:
            try:
                fee_structure = DegreeApplication.get_required_fee(
                    program.level,
                    application_type,
                    timing,
                    return_fee=True,
                )
            except ValidationError as exc:
                raise exc
            cleaned['challan_amount'] = fee_structure.amount
            cleaned['fee_timing_at_entry'] = timing
            cleaned['required_fee_at_entry'] = fee_structure.amount
            cleaned['fee_structure_at_entry'] = fee_structure
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.created_by = self.user
        obj.fee_timing_at_entry = self.cleaned_data['fee_timing_at_entry']
        obj.required_fee_at_entry = self.cleaned_data['required_fee_at_entry']
        obj.fee_structure_at_entry = self.cleaned_data.get('fee_structure_at_entry')
        obj.final_fee_timing = obj.fee_timing_at_entry
        obj.final_required_fee = obj.required_fee_at_entry
        # Removed from the visible form but still stored for compatibility.
        obj.declared_result_date = timezone.localdate()
        obj.session_year = ''
        all_docs_complete = all(self.checklist_data.values())
        obj.status = ApplicationStatus.PENDING_VERIFICATION if all_docs_complete else ApplicationStatus.DOCUMENTS_REQUIRED
        if commit:
            obj.save()
            ApplicationChecklist.objects.create(application=obj, checked_by=self.user, **self.checklist_data)
            ApplicationPayment.objects.create(
                application=obj,
                bank=self.cleaned_data['bank'],
                challan_no=self.cleaned_data['challan_no'],
                challan_date=self.cleaned_data['challan_date'],
                amount=self.cleaned_data['required_fee_at_entry'],
                created_by=self.user,
            )
        return obj


class AdminApplicationEditForm(forms.ModelForm):
    # Frontend accepts formatted CNIC like 17301-8021688-3 (15 chars).
    # clean_cnic() below strips dashes so the database still stores 13 digits only.
    cnic = forms.CharField(max_length=25, required=True, label='CNIC no')
    bank = forms.ModelChoiceField(queryset=Bank.objects.filter(is_active=True), required=True, empty_label='Select Bank')
    challan_no = forms.CharField(max_length=100, required=True, label='Challan no')
    challan_date = forms.DateField(
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                                'class': 'date-picker-input',
            },
        ),
        required=True,
        label='Challan date',
    )
    challan_amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False, disabled=True,
                                        label='Challan amount', help_text='Calculated automatically from the active fee schedule.')

    class Meta:
        model = DegreeApplication
        fields = [
            'student_name', 'father_name', 'cnic', 'mobile', 'email', 'registration_no', 'roll_no',
            'postal_address', 'program', 'institute', 'fee_timing_at_entry',
            'application_type', 'received_mode', 'status',
        ]
        widgets = {
            'postal_address': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'student_name': 'Name',
            'cnic': 'CNIC no',
            'roll_no': 'Roll No',
            'mobile': 'Mobile no',
            'email': 'Email address',
            'fee_timing_at_entry': 'Timing',
            'received_mode': 'Received mode',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program'].queryset = Program.objects.filter(is_active=True)
        self.fields['program'].empty_label = 'Select Program'
        self.fields['institute'].queryset = Institute.objects.filter(is_active=True)
        self.fields['institute'].empty_label = 'Select Institute'
        self.fields['bank'].empty_label = 'Select Bank'
        self.fields['fee_timing_at_entry'].choices = [('', 'Select Timing')] + list(FeeTiming.choices)
        self.fields['application_type'].choices = [('', 'Select Application Type')] + list(ApplicationType.choices)
        self.fields['received_mode'].choices = [('', 'Select Received Mode')] + list(ReceivingMode.choices)
        self.fields['status'].choices = list(ACTIVE_APPLICATION_STATUS_CHOICES)
        self.fields['challan_amount'].widget.attrs.update({'readonly': 'readonly', 'class': 'calculated-fee-input'})
        self.fields['email'].required = False
        self.fields['email'].widget.attrs.update({'placeholder': ''})
        self.fields['roll_no'].required = False
        self.fields['roll_no'].widget.attrs.update({'placeholder': ''})
        self.fields['cnic'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'cnic-input', 'placeholder': '00000-0000000-0'})
        self.fields['mobile'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'mobile-input', 'placeholder': ''})
        payment = self.instance.payments.order_by('created_at').first() if self.instance and self.instance.pk else None
        if payment and not self.is_bound:
            self.fields['bank'].initial = payment.bank
            self.fields['challan_no'].initial = payment.challan_no
            self.fields['challan_date'].initial = payment.challan_date
            self.fields['challan_amount'].initial = payment.amount
        elif self.instance and self.instance.pk and not self.is_bound:
            self.fields['challan_amount'].initial = self.instance.required_fee_at_entry
        self.order_fields([
            'student_name', 'father_name', 'cnic', 'mobile', 'email', 'registration_no', 'roll_no',
            'postal_address', 'program', 'institute', 'fee_timing_at_entry',
            'application_type', 'bank', 'challan_no', 'challan_date',
            'challan_amount', 'received_mode', 'status',
        ])

    def clean_cnic(self):
        value = normalize_cnic(self.cleaned_data.get('cnic'))
        if len(value) != 13:
            raise ValidationError('CNIC/Form-B must be 13 digits.')
        return value

    def clean_mobile(self):
        value = normalize_mobile(self.cleaned_data.get('mobile'))
        if len(value) != 11:
            raise ValidationError('Mobile no must be 11 digits.')
        return value

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get('program')
        timing = cleaned.get('fee_timing_at_entry')
        application_type = cleaned.get('application_type')
        if timing == FeeTiming.BEFORE_TIME:
            application_type = ApplicationType.URGENT
            cleaned['application_type'] = ApplicationType.URGENT
        if program and timing and application_type:
            fee_structure = DegreeApplication.get_required_fee(
                program.level,
                application_type,
                timing,
                on_date=self.instance.created_at.date() if self.instance and self.instance.created_at else None,
                return_fee=True,
            )
            cleaned['challan_amount'] = fee_structure.amount
            cleaned['fee_structure_at_entry'] = fee_structure
            cleaned['required_fee_at_entry'] = fee_structure.amount
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.fee_structure_at_entry = self.cleaned_data.get('fee_structure_at_entry')
        obj.required_fee_at_entry = self.cleaned_data.get('required_fee_at_entry')
        obj.final_fee_timing = obj.fee_timing_at_entry
        obj.final_required_fee = obj.required_fee_at_entry
        if commit:
            obj.save()
            payment = obj.payments.order_by('created_at').first()
            if payment is None:
                ApplicationPayment.objects.create(
                    application=obj,
                    bank=self.cleaned_data['bank'],
                    challan_no=self.cleaned_data['challan_no'],
                    challan_date=self.cleaned_data['challan_date'],
                    amount=self.cleaned_data['required_fee_at_entry'],
                    created_by=obj.created_by,
                )
            else:
                payment.bank = self.cleaned_data['bank']
                payment.challan_no = self.cleaned_data['challan_no']
                payment.challan_date = self.cleaned_data['challan_date']
                payment.amount = self.cleaned_data['required_fee_at_entry']
                payment.save(update_fields=['bank', 'challan_no', 'challan_date', 'amount'])
        return obj


class DocumentChecklistUpdateForm(ChecklistGateForm):
    pass


class VerificationForm(forms.Form):
    verified_result_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    remarks = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    def __init__(self, *args, **kwargs):
        self.application = kwargs.pop('application')
        super().__init__(*args, **kwargs)
        self.fields['verified_result_date'].initial = self.application.verified_result_date or self.application.declared_result_date

    def clean_verified_result_date(self):
        verified_date = self.cleaned_data['verified_result_date']
        if verified_date != self.application.declared_result_date:
            timing = DegreeApplication.calculate_timing(verified_date)
            required_fee = DegreeApplication.get_required_fee(
                self.application.program.level,
                self.application.application_type,
                timing,
                on_date=self.application.created_at.date() if self.application.created_at else None,
            )
            if self.application.total_paid != required_fee:
                raise ValidationError(
                    f'Fee mismatch after corrected declaration date. Required Rs. {required_fee}, paid Rs. {self.application.total_paid}. '
                    'Verification is blocked until correct fee is deposited.'
                )
        return verified_date


class PrintDetailForm(forms.ModelForm):
    class Meta:
        model = DegreeApplication
        fields = ['degree_book_no', 'degree_serial_no']
        labels = {
            'degree_book_no': 'Book No',
            'degree_serial_no': 'Degree Sheet Serial No',
        }
        widgets = {
            'degree_book_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter book no'}),
            'degree_serial_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter degree sheet serial no'}),
        }

    def clean_degree_book_no(self):
        value = (self.cleaned_data.get('degree_book_no') or '').strip()
        if not value:
            raise ValidationError('Book no is required before marking the degree as printed.')
        return value

    def clean_degree_serial_no(self):
        value = (self.cleaned_data.get('degree_serial_no') or '').strip()
        if not value:
            raise ValidationError('Degree sheet serial no is required before marking the degree as printed.')
        return value


class DeliveryForm(forms.ModelForm):
    # Override the model field so formatted CNIC values such as 00000-0000000-0
    # or manually typed values with spaces around dashes do not fail max_length
    # validation before clean_delivered_to_cnic() removes non-digits.
    delivered_to_cnic = forms.CharField(max_length=25, required=False, label='Representative CNIC')

    courier_company_choice = forms.ModelChoiceField(
        queryset=CourierCompany.objects.filter(is_active=True),
        required=False,
        empty_label='Select Courier Company',
        label='Courier company',
    )
    courier_date = forms.DateField(
        required=False,
        initial=timezone.localdate,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        label='Courier date',
    )

    class Meta:
        model = DegreeApplication
        fields = [
            'delivery_mode',
            'delivered_to_name',
            'delivered_to_cnic',
            'delivered_to_mobile',
            'courier_tracking_no',
            'courier_date',
        ]
        labels = {
            'delivered_to_name': 'Representative name',
            'delivered_to_cnic': 'Representative CNIC',
            'delivered_to_mobile': 'Representative mobile no',
            'courier_tracking_no': 'Tracking ID',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['delivery_mode'].choices = [('', 'Select delivery mode')] + list(ReceivingMode.choices)
        self.fields['delivery_mode'].required = True
        self.fields['delivered_to_cnic'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'cnic-input', 'placeholder': '00000-0000000-0'})
        self.fields['delivered_to_mobile'].widget.attrs.update({'inputmode': 'numeric', 'autocomplete': 'off', 'class': 'mobile-input', 'placeholder': ''})
        self.fields['courier_tracking_no'].widget.attrs.update({'placeholder': 'Courier tracking ID'})
        if self.instance and self.instance.pk and self.instance.courier_company and not self.is_bound:
            self.fields['courier_company_choice'].initial = CourierCompany.objects.filter(name=self.instance.courier_company).first()

    def clean_delivered_to_cnic(self):
        value = normalize_cnic(self.cleaned_data.get('delivered_to_cnic'))
        if value and len(value) != 13:
            raise ValidationError('Representative CNIC must be 13 digits.')
        return value

    def clean_delivered_to_mobile(self):
        value = normalize_mobile(self.cleaned_data.get('delivered_to_mobile'))
        if value and len(value) != 11:
            raise ValidationError('Representative mobile no must be 11 digits.')
        return value

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('delivery_mode')
        if mode == ReceivingMode.SELF:
            cleaned['delivered_to_name'] = ''
            cleaned['delivered_to_cnic'] = ''
            cleaned['delivered_to_mobile'] = ''
            cleaned['courier_tracking_no'] = ''
            cleaned['courier_date'] = None
        elif mode == ReceivingMode.REPRESENTATIVE:
            for field in ['delivered_to_name', 'delivered_to_cnic', 'delivered_to_mobile']:
                if not cleaned.get(field):
                    self.add_error(field, 'This field is required for representative delivery.')
            cleaned['courier_tracking_no'] = ''
            cleaned['courier_date'] = None
        elif mode == ReceivingMode.COURIER:
            if not cleaned.get('courier_company_choice'):
                self.add_error('courier_company_choice', 'Courier company is required for courier delivery.')
            if not cleaned.get('courier_tracking_no'):
                self.add_error('courier_tracking_no', 'Tracking ID is required for courier delivery.')
            if not cleaned.get('courier_date'):
                self.add_error('courier_date', 'Courier date is required for courier delivery.')
            cleaned['delivered_to_name'] = ''
            cleaned['delivered_to_cnic'] = ''
            cleaned['delivered_to_mobile'] = ''
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        company = self.cleaned_data.get('courier_company_choice')
        if obj.delivery_mode == ReceivingMode.COURIER and company:
            obj.courier_company = company.name
        else:
            obj.courier_company = ''
        if commit:
            obj.save()
        return obj


class StatusRemarksForm(forms.Form):
    remarks = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)


class FeeStructureForm(forms.ModelForm):
    replace_current = forms.BooleanField(
        required=False,
        initial=True,
        label='Replace current fee automatically',
        help_text='Recommended. The old fee is closed one day before the new effective date and remains available for history.'
    )

    class Meta:
        model = FeeStructure
        # Timing is intentionally before application_type in the UI.
        # If timing is BEFORE_TIME, the fee must be created as URGENT automatically.
        fields = ['program_level', 'timing', 'application_type', 'amount', 'effective_from', 'remarks', 'is_active']
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Example: Fee revised by notification dated 2026-05-01'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['program_level'].choices = [('', 'Select Program Level')] + list(Program.Level.choices)
        self.fields['timing'].choices = [('', 'Select Timing')] + list(FeeTiming.choices)
        self.fields['application_type'].choices = [('', 'Select Application Type')] + list(ApplicationType.choices)
        self.fields['application_type'].required = False
        self.fields['application_type'].help_text = 'Automatically set to Urgent when Timing is Before Time.'
        if not self.instance.pk:
            self.fields['effective_from'].initial = timezone.localdate()
        if self.instance and self.instance.pk:
            self.fields.pop('replace_current')
            self.fields['effective_from'].disabled = True
            self.fields['program_level'].disabled = True
            self.fields['timing'].disabled = True
            self.fields['application_type'].disabled = True
            self.fields['is_active'].help_text = 'Use inactive only to retire a wrong future fee. Do not edit old applied fees.'

    def clean(self):
        cleaned = super().clean()
        timing = cleaned.get('timing')
        application_type = cleaned.get('application_type')
        if timing == FeeTiming.BEFORE_TIME:
            cleaned['application_type'] = ApplicationType.URGENT
        elif not application_type:
            self.add_error('application_type', 'Application type is required unless timing is Before Time.')
        return cleaned

    def save(self, commit=True):
        if not self.instance.pk:
            self.fields['effective_from'].initial = timezone.localdate()
        if self.instance and self.instance.pk:
            return super().save(commit=commit)
        if self.cleaned_data.get('replace_current'):
            return FeeStructure.replace_current(
                program_level=self.cleaned_data['program_level'],
                application_type=self.cleaned_data['application_type'],
                timing=self.cleaned_data['timing'],
                amount=self.cleaned_data['amount'],
                effective_from=self.cleaned_data['effective_from'],
                created_by=self.user,
                remarks=self.cleaned_data.get('remarks') or '',
            )
        obj = super().save(commit=False)
        obj.created_by = self.user
        if commit:
            obj.save()
        return obj


class VCFileCreateForm(forms.Form):
    applications = forms.ModelMultipleChoiceField(
        queryset=DegreeApplication.objects.filter(status=ApplicationStatus.PRINTED_PENDING_SIGNATURE, vc_file_item__isnull=True),
        widget=forms.CheckboxSelectMultiple,
    )
    remarks = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)
