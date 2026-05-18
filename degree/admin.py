from django.contrib import admin
from .models import (
    ApplicationChecklist,
    ApplicationPayment,
    ApplicationStatusLog,
    DegreeApplication,
    FeeStructure,
    VCFile,
    VCFileItem,
)


class PaymentInline(admin.TabularInline):
    model = ApplicationPayment
    extra = 0


class ChecklistInline(admin.StackedInline):
    model = ApplicationChecklist
    can_delete = False


@admin.register(DegreeApplication)
class DegreeApplicationAdmin(admin.ModelAdmin):
    list_display = ('tracking_no', 'student_name', 'registration_no', 'cnic', 'email', 'program', 'status', 'application_type', 'created_at')
    list_filter = ('status', 'application_type', 'program__level', 'created_at')
    search_fields = ('tracking_no', 'student_name', 'father_name', 'cnic', 'email', 'registration_no', 'roll_no')
    readonly_fields = ('tracking_no', 'created_at', 'updated_at')
    inlines = [ChecklistInline, PaymentInline]


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('program_level', 'application_type', 'timing', 'amount', 'is_active')
    list_filter = ('program_level', 'application_type', 'timing', 'is_active')


@admin.register(ApplicationPayment)
class ApplicationPaymentAdmin(admin.ModelAdmin):
    list_display = ('application', 'bank', 'challan_no', 'challan_date', 'amount', 'payment_type')
    search_fields = ('application__tracking_no', 'challan_no')


@admin.register(ApplicationStatusLog)
class ApplicationStatusLogAdmin(admin.ModelAdmin):
    list_display = ('application', 'from_status', 'to_status', 'changed_by', 'created_at')
    list_filter = ('to_status', 'created_at')


class VCFileItemInline(admin.TabularInline):
    model = VCFileItem
    extra = 0


@admin.register(VCFile)
class VCFileAdmin(admin.ModelAdmin):
    list_display = ('file_no', 'status', 'created_by', 'created_at', 'submitted_at', 'returned_at')
    list_filter = ('status', 'created_at')
    inlines = [VCFileItemInline]
