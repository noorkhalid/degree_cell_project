from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, connection
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q, Value
from django.db.models.functions import Replace
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook
from accounts.models import UserProfile
from academics.models import Program
from .forms import (
    AdminApplicationEditForm,
    ChecklistGateForm,
    DegreeApplicationForm,
    DocumentChecklistUpdateForm,
    DeliveryForm,
    FeeStructureForm,
    PrintDetailForm,
    StatusRemarksForm,
    VCFileCreateForm,
    VerificationForm,
)
from .models import ACTIVE_APPLICATION_STATUS_CHOICES, APPLICATION_FILTER_STATUS_CHOICES, LEGACY_STATUS_MAP, ApplicationStatus, ApplicationStatusLog, ApplicationType, DegreeApplication, FeeStructure, FeeTiming, VCFile, VCFileItem
from .permissions import is_admin, is_desk, is_printing, role_required


def ensure_compatible_schema():
    """Small development-safety guard for existing SQLite databases.
    Adds newly introduced nullable/default columns that old local db.sqlite3 files may not have yet.
    Proper deployments should still run: python manage.py makemigrations && python manage.py migrate.
    """
    if connection.vendor != 'sqlite':
        return
    table_name = DegreeApplication._meta.db_table
    try:
        with connection.cursor() as cursor:
            existing_tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if table_name not in existing_tables:
                return
            columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
            if 'email' not in columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN email varchar(254) NOT NULL DEFAULT ''")
            if 'roll_no' not in columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN roll_no varchar(100) NOT NULL DEFAULT ''")
            # Normalize old detailed workflow statuses into the four dashboard statuses.
            for old_status, new_status in LEGACY_STATUS_MAP.items():
                cursor.execute(f"UPDATE {table_name} SET status = ? WHERE status = ?", [new_status, old_status])
    except Exception:
        # Do not hide real application errors on non-compatible databases; migrations remain the source of truth.
        pass


def format_cnic_for_display(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(digits) == 13:
        return f'{digits[:5]}-{digits[5:12]}-{digits[12]}'
    return str(value or '')


def log_status(application, user, old_status, new_status, remarks=''):
    ApplicationStatusLog.objects.create(
        application=application,
        from_status=old_status or '',
        to_status=new_status,
        changed_by=user,
        remarks=remarks,
    )


@login_required
def dashboard(request):
    ensure_compatible_schema()
    counts = DegreeApplication.objects.values('status').annotate(total=Count('id'))
    status_counts = {item['status']: item['total'] for item in counts}

    # Count both current status codes and old/legacy codes, so existing local data
    # is still reflected correctly on the dashboard.
    dashboard_counts = {
        'submitted': status_counts.get(ApplicationStatus.SUBMITTED, 0),
        'in_process': (
            status_counts.get(ApplicationStatus.PENDING_VERIFICATION, 0)
            + status_counts.get('IN_PROCESS', 0)
        ),
        'objection': (
            status_counts.get(ApplicationStatus.DOCUMENTS_REQUIRED, 0)
            + status_counts.get('OBJECTION', 0)
        ),
        'printed': (
            status_counts.get(ApplicationStatus.PRINTED_PENDING_SIGNATURE, 0)
            + status_counts.get('PRINTED', 0)
        ),
        'vc_file': status_counts.get(ApplicationStatus.VC_FILE, 0),
        # READY_FOR_COLLECTION is already the current database status code.
        # Do not add status_counts.get('READY_FOR_COLLECTION') again, because
        # ApplicationStatus.READY_FOR_COLLECTION equals the same string and would double-count.
        'ready_for_collection': status_counts.get(ApplicationStatus.READY_FOR_COLLECTION, 0),
    }

    recent = DegreeApplication.objects.select_related('campus', 'department', 'program').order_by('-created_at')[:10]
    return render(request, 'degree/dashboard.html', {
        'status_counts': status_counts,
        'dashboard_counts': dashboard_counts,
        'recent': recent,
        'statuses': ACTIVE_APPLICATION_STATUS_CHOICES,
    })


@role_required(UserProfile.Role.DESK)
def application_create(request):
    ensure_compatible_schema()
    checklist_form = ChecklistGateForm(request.POST or None)
    form = None
    duplicate_matches = []
    if request.method == 'POST':
        checklist_form.is_valid()
        checklist_data = checklist_form.cleaned_data if checklist_form.is_valid() else {}
        form = DegreeApplicationForm(request.POST, user=request.user, checklist_data=checklist_data)
        cnic = request.POST.get('cnic', '').replace('-', '').strip()
        reg = request.POST.get('registration_no', '').strip()
        if cnic or reg:
            duplicate_matches = DegreeApplication.objects.filter(Q(cnic=cnic) | Q(registration_no=reg)).order_by('-created_at')[:5]
        if form.is_valid():
            app = form.save()
            if app.status == ApplicationStatus.DOCUMENTS_REQUIRED:
                log_status(app, request.user, '', app.status, 'Application saved but documents are incomplete. Processing is blocked until documents are completed.')
                messages.warning(request, f'Application saved. Tracking Number: {app.tracking_no}. Status: Objection.')
            else:
                log_status(app, request.user, '', app.status, 'Application received with complete documents. Status: In Process.')
                messages.success(request, f'Application saved. Tracking Number: {app.tracking_no}')
            return redirect('degree:detail', pk=app.pk)
    else:
        form = DegreeApplicationForm(user=request.user, checklist_data={})
    return render(request, 'degree/application_form.html', {'checklist_form': checklist_form, 'form': form, 'duplicate_matches': duplicate_matches})


@login_required
def get_application_fee(request):
    program_id = request.GET.get('program')
    timing = request.GET.get('timing')
    application_type = request.GET.get('application_type')
    if not program_id or not timing or not application_type:
        return JsonResponse({'ok': False, 'amount': '', 'message': 'Select Program, Timing, and Application Type.'})

    if timing == FeeTiming.BEFORE_TIME:
        application_type = ApplicationType.URGENT

    program = get_object_or_404(Program, pk=program_id)
    fee = FeeStructure.get_applicable(program.level, application_type, timing)
    if not fee:
        return JsonResponse({
            'ok': False,
            'amount': '',
            'message': 'No active fee found for this Program Level, Timing, and Application Type.',
            'application_type': application_type,
            'timing': timing,
        })
    return JsonResponse({
        'ok': True,
        'amount': str(fee.amount),
        'timing': timing,
        'timing_label': dict(FeeTiming.choices)[timing],
        'application_type': application_type,
        'application_type_label': dict(ApplicationType.choices)[application_type],
        'program_level': program.level,
    })



PUBLIC_STANDARD_STATUS_STEPS = [
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.PENDING_VERIFICATION,
    ApplicationStatus.PRINTED_PENDING_SIGNATURE,
    ApplicationStatus.VC_FILE,
    ApplicationStatus.READY_FOR_COLLECTION,
    ApplicationStatus.DELIVERED,
]

PUBLIC_OBJECTION_STATUS_STEPS = [
    ApplicationStatus.DOCUMENTS_REQUIRED,
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.PENDING_VERIFICATION,
    ApplicationStatus.PRINTED_PENDING_SIGNATURE,
    ApplicationStatus.VC_FILE,
    ApplicationStatus.READY_FOR_COLLECTION,
    ApplicationStatus.DELIVERED,
]

PUBLIC_STATUS_ICONS = {
    ApplicationStatus.SUBMITTED: 'bi-send-check-fill',
    ApplicationStatus.DOCUMENTS_REQUIRED: 'bi-exclamation-circle-fill',
    ApplicationStatus.PENDING_VERIFICATION: 'bi-hourglass-split',
    ApplicationStatus.PRINTED_PENDING_SIGNATURE: 'bi-printer-fill',
    ApplicationStatus.VC_FILE: 'bi-folder-check',
    ApplicationStatus.READY_FOR_COLLECTION: 'bi-check2-circle',
    ApplicationStatus.DELIVERED: 'bi-award-fill',
    ApplicationStatus.CANCELLED: 'bi-x-octagon-fill',
}

PUBLIC_STATUS_CLASSES = {
    ApplicationStatus.SUBMITTED: 'submitted',
    ApplicationStatus.DOCUMENTS_REQUIRED: 'objection',
    ApplicationStatus.PENDING_VERIFICATION: 'process',
    ApplicationStatus.PRINTED_PENDING_SIGNATURE: 'printed',
    ApplicationStatus.VC_FILE: 'vc-file',
    ApplicationStatus.READY_FOR_COLLECTION: 'ready',
    ApplicationStatus.DELIVERED: 'collected',
    ApplicationStatus.CANCELLED: 'cancelled',
}


def application_has_objection_history(app, display_status):
    """Return True when this application is/was ever in Objection.

    Current Objection must be shown as the first public step. If an application
    never had Objection, the Objection stage is removed from student tracking.
    """
    if display_status == ApplicationStatus.DOCUMENTS_REQUIRED:
        return True
    try:
        return app.status_logs.filter(
            Q(to_status=ApplicationStatus.DOCUMENTS_REQUIRED) |
            Q(from_status=ApplicationStatus.DOCUMENTS_REQUIRED) |
            Q(to_status='OBJECTION') |
            Q(from_status='OBJECTION')
        ).exists()
    except Exception:
        return False


def prepare_public_tracking_application(app):
    """Attach display-only tracking helpers for the public tracking page.

    Public tracking now uses two flows:
    1. Normal applications: Submitted -> In Process -> Printed -> VC File -> Ready for Collection -> Collected
    2. Applications that are/were in Objection: Objection -> Submitted -> In Process -> Printed -> VC File -> Ready for Collection -> Collected
    """
    display_status = LEGACY_STATUS_MAP.get(app.status, app.status)
    has_objection_history = application_has_objection_history(app, display_status)
    status_steps = PUBLIC_OBJECTION_STATUS_STEPS if has_objection_history else PUBLIC_STANDARD_STATUS_STEPS

    if display_status == ApplicationStatus.CANCELLED:
        step_index = 0
        progress = 100
    else:
        try:
            step_index = status_steps.index(display_status)
        except ValueError:
            step_index = 0
        progress = round(((step_index + 1) / len(status_steps)) * 100)

    public_steps = []
    for index, status in enumerate(status_steps):
        public_steps.append({
            'code': status,
            'label': ApplicationStatus(status).label,
            'icon': PUBLIC_STATUS_ICONS.get(status, 'bi-circle-fill'),
            'state': 'done' if index < step_index else ('current' if index == step_index else 'pending'),
        })

    missing_documents = []
    try:
        checklist = app.checklist
    except Exception:
        checklist = None
    if checklist:
        missing_documents = list(checklist.missing_documents)

    # Show the missing-documents box only when the application is currently in Objection.
    if display_status != ApplicationStatus.DOCUMENTS_REQUIRED:
        missing_documents = []
    elif not missing_documents:
        missing_documents = ['Required documents are incomplete. Please contact Degree Cell for details.']

    app.public_display_status = display_status
    app.public_display_status_label = ApplicationStatus(display_status).label if display_status in ApplicationStatus.values else app.get_status_display()
    app.public_progress = progress
    app.public_steps = public_steps
    app.public_status_class = PUBLIC_STATUS_CLASSES.get(display_status, 'process')
    app.public_status_icon = PUBLIC_STATUS_ICONS.get(display_status, 'bi-info-circle-fill')
    app.public_missing_documents = missing_documents
    app.public_has_objection_history = has_objection_history
    return app

def public_tracking(request):
    """Public CNIC-based degree application tracking page.

    This page intentionally has no login_required decorator so students can
    check their processing history from outside the staff portal.
    """
    ensure_compatible_schema()
    raw_cnic = (request.GET.get('cnic') or '').strip()
    cnic_digits = ''.join(ch for ch in raw_cnic if ch.isdigit())
    applications = []
    searched = False
    error = ''

    if raw_cnic:
        searched = True
        if len(cnic_digits) != 13:
            error = 'Please enter a valid 13-digit CNIC number.'
        else:
            cnic_formatted = format_cnic_for_display(cnic_digits)
            applications = list(
                DegreeApplication.objects
                .select_related('campus', 'department', 'program', 'checklist')
                .prefetch_related('status_logs')
                .annotate(
                    cnic_no_dash=Replace(Replace('cnic', Value('-'), Value('')), Value(' '), Value(''))
                )
                .filter(Q(cnic=cnic_digits) | Q(cnic=cnic_formatted) | Q(cnic_no_dash=cnic_digits))
                .order_by('-created_at')
            )
            applications = [prepare_public_tracking_application(app) for app in applications]

    return render(request, 'degree/public_tracking.html', {
        'cnic': raw_cnic,
        'cnic_digits': cnic_digits,
        'searched': searched,
        'error': error,
        'applications': applications,
    })


def public_receipt(request, tracking_no):
    """Public printable receipt, protected by matching CNIC query parameter."""
    ensure_compatible_schema()
    cnic_digits = ''.join(ch for ch in (request.GET.get('cnic') or '').strip() if ch.isdigit())
    app = get_object_or_404(
        DegreeApplication.objects.select_related('campus', 'department', 'program', 'checklist').prefetch_related('status_logs'),
        tracking_no=tracking_no
    )
    app_cnic = ''.join(ch for ch in str(app.cnic or '') if ch.isdigit())
    if len(cnic_digits) != 13 or cnic_digits != app_cnic:
        return render(request, 'degree/public_receipt.html', {
            'app': None,
            'error': 'Invalid receipt link. Please search again with the correct CNIC number.',
        }, status=403)
    app = prepare_public_tracking_application(app)
    return render(request, 'degree/public_receipt.html', {'app': app, 'error': ''})


@role_required(UserProfile.Role.DESK)
def update_documents(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk)
    checklist = getattr(app, 'checklist', None)
    initial = {}
    if checklist:
        for field in DocumentChecklistUpdateForm.base_fields:
            initial[field] = getattr(checklist, field, False)
    form = DocumentChecklistUpdateForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        if checklist is None:
            from .models import ApplicationChecklist
            checklist = ApplicationChecklist.objects.create(application=app, checked_by=request.user, **data)
        else:
            for field, value in data.items():
                setattr(checklist, field, value)
            checklist.checked_by = request.user
            checklist.save()
        old = app.status
        if checklist.is_complete and app.status == ApplicationStatus.DOCUMENTS_REQUIRED:
            app.status = ApplicationStatus.SUBMITTED
            app.save(update_fields=['status', 'updated_at'])
            log_status(app, request.user, old, app.status, 'Required documents completed. Application is now Submitted.')
            messages.success(request, 'Documents completed. Application is now Submitted.')
        elif not checklist.is_complete:
            app.status = ApplicationStatus.DOCUMENTS_REQUIRED
            app.save(update_fields=['status', 'updated_at'])
            log_status(app, request.user, old, app.status, 'Document checklist updated but still incomplete.')
            messages.warning(request, 'Checklist saved. Application still requires documents.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/document_checklist_form.html', {'app': app, 'form': form})


@login_required
def fee_structure_list(request):
    qs = FeeStructure.objects.all()
    program_level = request.GET.get('program_level', '')
    application_type = request.GET.get('application_type', '')
    timing = request.GET.get('timing', '')
    status = request.GET.get('status', '')
    if program_level:
        qs = qs.filter(program_level=program_level)
    if application_type:
        qs = qs.filter(application_type=application_type)
    if timing:
        qs = qs.filter(timing=timing)
    today = timezone.localdate()
    if status == 'current':
        qs = qs.filter(is_active=True, effective_from__lte=today).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
    elif status == 'future':
        qs = qs.filter(is_active=True, effective_from__gt=today)
    elif status == 'history':
        qs = qs.filter(Q(is_active=False) | Q(effective_to__lt=today))
    return render(request, 'degree/fee_structure_list.html', {
        'items': qs,
        'program_levels': FeeStructure._meta.get_field('program_level').choices,
        'application_types': FeeStructure._meta.get_field('application_type').choices,
        'timings': FeeStructure._meta.get_field('timing').choices,
    })


@role_required(UserProfile.Role.ADMIN)
def fee_structure_create(request):
    form = FeeStructureForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'New fee structure saved. Previous applicable fee was closed automatically and remains in history.')
        return redirect('degree:fee_structures')
    return render(request, 'degree/fee_structure_form.html', {'form': form, 'title': 'Add Fee Structure'})


@role_required(UserProfile.Role.ADMIN)
def fee_structure_edit(request, pk):
    fee = get_object_or_404(FeeStructure, pk=pk)
    form = FeeStructureForm(request.POST or None, instance=fee, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Fee structure updated.')
        return redirect('degree:fee_structures')
    return render(request, 'degree/fee_structure_form.html', {'form': form, 'title': 'Edit Fee Structure'})




@role_required(UserProfile.Role.DESK)
def handover_slip(request):
    """Print a handover slip and move selected Submitted applications to In Process."""
    q = request.GET.get('q', '').strip()
    eligible = DegreeApplication.objects.select_related('campus', 'department', 'program').filter(
        status=ApplicationStatus.SUBMITTED
    )
    if q:
        eligible = eligible.filter(
            Q(tracking_no__icontains=q) | Q(student_name__icontains=q) | Q(father_name__icontains=q) |
            Q(cnic__icontains=q) | Q(registration_no__icontains=q) | Q(roll_no__icontains=q) |
            Q(program__name__icontains=q)
        )

    selected_apps = []
    if request.method == 'POST':
        selected_ids = request.POST.getlist('application_ids')
        if not selected_ids:
            messages.error(request, 'Select at least one application to print the handover slip.')
            return redirect('degree:handover_slip')
        selected_apps = list(
            DegreeApplication.objects.select_related('campus', 'department', 'program')
            .filter(pk__in=selected_ids, status=ApplicationStatus.SUBMITTED)
            .order_by('student_name', 'registration_no')
        )
        if not selected_apps:
            messages.error(request, 'Selected applications are not eligible. Only Submitted applications can be printed on the handover slip.')
            return redirect('degree:handover_slip')
        with transaction.atomic():
            for app in selected_apps:
                old_status = app.status
                app.status = ApplicationStatus.PENDING_VERIFICATION
                app.save(update_fields=['status', 'updated_at'])
                log_status(app, request.user, old_status, app.status, 'Handover slip printed; moved to In Process.')
        return render(request, 'degree/handover_slip_print.html', {
            'applications': selected_apps,
            'printed_at': timezone.now(),
            'prepared_by': request.user,
        })

    return render(request, 'degree/handover_slip.html', {
        'applications': eligible.order_by('-updated_at')[:300],
        'q': q,
    })


@role_required(UserProfile.Role.DESK)
def application_processing(request):
    """Card-based processing desk with only logical next-step movements."""
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', ApplicationStatus.SUBMITTED).strip() or ApplicationStatus.SUBMITTED

    card_statuses = [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.DOCUMENTS_REQUIRED,
        ApplicationStatus.PENDING_VERIFICATION,
        ApplicationStatus.PRINTED_PENDING_SIGNATURE,
        ApplicationStatus.VC_FILE,
        ApplicationStatus.READY_FOR_COLLECTION,
    ]
    status_cards = []
    for status in card_statuses:
        status_cards.append({
            'code': status,
            'label': ApplicationStatus(status).label,
            'count': DegreeApplication.objects.filter(status=status).count(),
        })

    qs = DegreeApplication.objects.select_related('campus', 'department', 'program').filter(status=status_filter)
    if q:
        qs = qs.filter(
            Q(tracking_no__icontains=q) | Q(student_name__icontains=q) | Q(father_name__icontains=q) |
            Q(cnic__icontains=q) | Q(email__icontains=q) | Q(registration_no__icontains=q) | Q(roll_no__icontains=q)
        )

    next_status_map = {
        ApplicationStatus.SUBMITTED: ApplicationStatus.PENDING_VERIFICATION,
        ApplicationStatus.DOCUMENTS_REQUIRED: ApplicationStatus.SUBMITTED,
        ApplicationStatus.PENDING_VERIFICATION: ApplicationStatus.PRINTED_PENDING_SIGNATURE,
        ApplicationStatus.PRINTED_PENDING_SIGNATURE: ApplicationStatus.VC_FILE,
        ApplicationStatus.VC_FILE: ApplicationStatus.READY_FOR_COLLECTION,
        ApplicationStatus.READY_FOR_COLLECTION: ApplicationStatus.DELIVERED,
    }
    next_status = next_status_map.get(status_filter)
    next_label = ApplicationStatus(next_status).label if next_status else ''

    if request.method == 'POST':
        selected_ids = request.POST.getlist('application_ids')
        action = request.POST.get('action', '').strip()
        if not selected_ids:
            messages.error(request, 'Select at least one application.')
            return redirect(f'{request.path}?status={status_filter}&q={q}')

        apps = list(DegreeApplication.objects.select_related('campus', 'department', 'program').filter(pk__in=selected_ids, status=status_filter).distinct())
        if not apps:
            messages.error(request, 'No matching applications found for this status.')
            return redirect(f'{request.path}?status={status_filter}&q={q}')

        # Objection -> Submitted is allowed only when documents are complete.
        if action == 'advance' and status_filter == ApplicationStatus.DOCUMENTS_REQUIRED:
            updated, skipped = 0, []
            with transaction.atomic():
                for app in apps:
                    checklist = getattr(app, 'checklist', None)
                    if not checklist or not checklist.is_complete:
                        skipped.append(f'{app.tracking_no}: documents still incomplete')
                        continue
                    old = app.status
                    app.status = ApplicationStatus.SUBMITTED
                    app.save(update_fields=['status', 'updated_at'])
                    log_status(app, request.user, old, app.status, 'Moved from Objection to Submitted from processing desk.')
                    updated += 1
            if updated:
                messages.success(request, f'{updated} application(s) moved to Submitted.')
            if skipped:
                messages.warning(request, 'Skipped: ' + '; '.join(skipped[:8]) + (' ...' if len(skipped) > 8 else ''))

        elif action == 'advance' and status_filter == ApplicationStatus.SUBMITTED:
            messages.info(request, 'Use Print Handover Slip. Selected Submitted applications become In Process automatically when the slip is printed.')
            return redirect('degree:handover_slip')

        elif action == 'advance' and status_filter == ApplicationStatus.PENDING_VERIFICATION:
            messages.info(request, 'Printed status requires Book No and Degree Sheet Serial No. Use Enter Print Details; the status becomes Printed automatically after saving.')
            return redirect('degree:bulk_mark_printed')

        elif action == 'advance' and status_filter == ApplicationStatus.PRINTED_PENDING_SIGNATURE:
            with transaction.atomic():
                vc_file = VCFile.objects.create(created_by=request.user, remarks='Created from Processing Desk.')
                for idx, app in enumerate(apps, start=1):
                    if hasattr(app, 'vc_file_item'):
                        continue
                    VCFileItem.objects.create(vc_file=vc_file, application=app, serial_no=idx)
                    old = app.status
                    app.status = ApplicationStatus.VC_FILE
                    app.save(update_fields=['status', 'updated_at'])
                    log_status(app, request.user, old, app.status, f'VC file {vc_file.file_no} created from processing desk.')
            messages.success(request, f'VC file {vc_file.file_no} created. Selected applications moved to VC File.')
            return redirect('degree:vc_file_detail', pk=vc_file.pk)

        elif action == 'advance' and status_filter == ApplicationStatus.VC_FILE:
            updated = 0
            with transaction.atomic():
                for app in apps:
                    old = app.status
                    app.status = ApplicationStatus.READY_FOR_COLLECTION
                    app.save(update_fields=['status', 'updated_at'])
                    log_status(app, request.user, old, app.status, 'Marked Ready for Collection from processing desk.')
                    updated += 1
            messages.success(request, f'{updated} application(s) moved to Ready for Collection.')

        elif action == 'advance' and status_filter == ApplicationStatus.READY_FOR_COLLECTION:
            if len(apps) == 1:
                return redirect('degree:deliver', pk=apps[0].pk)
            messages.info(request, 'Collection/delivery needs receiver details. Open each application and deliver it individually.')

        return redirect(f'{request.path}?status={status_filter}&q={q}')

    return render(request, 'degree/application_processing.html', {
        'applications': qs.order_by('-updated_at')[:300],
        'status_cards': status_cards,
        'statuses': ACTIVE_APPLICATION_STATUS_CHOICES,
        'selected_status': status_filter,
        'q': q,
        'next_status': next_status,
        'next_label': next_label,
    })


@login_required
def application_list(request):
    ensure_compatible_schema()
    qs = DegreeApplication.objects.select_related('campus', 'department', 'program').all()
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    app_type = request.GET.get('application_type', '')
    if q:
        qs = qs.filter(
            Q(tracking_no__icontains=q) | Q(student_name__icontains=q) | Q(father_name__icontains=q) |
            Q(cnic__icontains=q) | Q(email__icontains=q) | Q(registration_no__icontains=q) | Q(roll_no__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if app_type:
        qs = qs.filter(application_type=app_type)
    return render(request, 'degree/application_list.html', {'applications': qs[:300], 'statuses': APPLICATION_FILTER_STATUS_CHOICES, 'can_admin_manage': is_admin(request.user)})


@login_required
def application_detail(request, pk):
    ensure_compatible_schema()
    app = get_object_or_404(DegreeApplication.objects.select_related('campus', 'department', 'program'), pk=pk)
    logs = app.status_logs.select_related('changed_by')[:20]
    return render(request, 'degree/application_detail.html', {'app': app, 'logs': logs, 'can_admin_manage': is_admin(request.user)})


@role_required(UserProfile.Role.ADMIN)
def application_edit(request, pk):
    app = get_object_or_404(DegreeApplication.objects.select_related('campus', 'department', 'program'), pk=pk)
    old_status = app.status
    form = AdminApplicationEditForm(request.POST or None, instance=app)
    if request.method == 'POST' and form.is_valid():
        app = form.save()
        if old_status != app.status:
            log_status(app, request.user, old_status, app.status, 'Application edited by admin.')
        messages.success(request, f'Application {app.tracking_no} updated successfully.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/application_edit.html', {'app': app, 'form': form})


@role_required(UserProfile.Role.ADMIN)
def application_delete(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk)
    if request.method == 'POST':
        tracking_no = app.tracking_no
        try:
            app.delete()
        except ProtectedError:
            messages.error(request, 'This application cannot be deleted because it is linked with a protected workflow record, such as a VC file. Cancel it instead if it should not be processed.')
            return redirect('degree:detail', pk=pk)
        messages.success(request, f'Application {tracking_no} deleted successfully.')
        return redirect('degree:list')
    return render(request, 'degree/application_delete_confirm.html', {'app': app})


@login_required
def receipt(request, pk):
    app = get_object_or_404(DegreeApplication.objects.select_related('program'), pk=pk)
    return render(request, 'degree/receipt.html', {'app': app})


@role_required(UserProfile.Role.DESK)
def verify_application(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk, status=ApplicationStatus.PENDING_VERIFICATION)
    form = VerificationForm(request.POST or None, application=app)
    if request.method == 'POST' and form.is_valid():
        verified_date = form.cleaned_data['verified_result_date']
        old = app.status
        app.verified_result_date = verified_date
        if verified_date != app.declared_result_date:
            app.final_fee_timing = DegreeApplication.calculate_timing(verified_date)
            app.final_required_fee = DegreeApplication.get_required_fee(
                app.program.level,
                app.application_type,
                app.final_fee_timing,
                on_date=app.created_at.date() if app.created_at else None,
            )
        else:
            app.final_fee_timing = app.fee_timing_at_entry
            app.final_required_fee = app.required_fee_at_entry
        app.status = ApplicationStatus.PENDING_VERIFICATION
        app.save()
        log_status(app, request.user, old, app.status, form.cleaned_data.get('remarks', 'Verified.'))
        messages.success(request, 'Application verified.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/verify.html', {'app': app, 'form': form})


@role_required(UserProfile.Role.DESK)
def send_for_printing(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk, status=ApplicationStatus.PENDING_VERIFICATION)
    form = StatusRemarksForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        old = app.status
        app.status = ApplicationStatus.PENDING_VERIFICATION
        app.save(update_fields=['status', 'updated_at'])
        log_status(app, request.user, old, app.status, form.cleaned_data.get('remarks', 'Sent for printing.'))
        messages.success(request, 'Application sent for printing.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/simple_action.html', {'app': app, 'form': form, 'title': 'Send for Printing'})


@role_required(UserProfile.Role.PRINTING)
def receive_for_print(request, pk):
    messages.info(request, 'Use Print Details to enter the book number and sheet serial number. The status will become Printed automatically after saving.')
    return redirect('degree:mark_printed', pk=pk)


@role_required(UserProfile.Role.PRINTING)
def mark_printed(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk, status=ApplicationStatus.PENDING_VERIFICATION)
    form = PrintDetailForm(request.POST or None, instance=app)
    if request.method == 'POST' and form.is_valid():
        old = app.status
        app = form.save(commit=False)
        app.status = ApplicationStatus.PRINTED_PENDING_SIGNATURE
        app.printed_by = request.user
        app.printed_at = timezone.now()
        app.save()
        log_status(app, request.user, old, app.status, 'Degree printed with sheet serial/book number.')
        messages.success(request, f'{app.tracking_no} marked as Printed.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/print_detail_form.html', {'app': app, 'form': form})


@role_required(UserProfile.Role.PRINTING)
def bulk_mark_printed(request):
    pending_apps = DegreeApplication.objects.select_related('campus', 'department', 'program').filter(
        status=ApplicationStatus.PENDING_VERIFICATION
    ).order_by('tracking_no')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('application_ids')
        if not selected_ids:
            messages.error(request, 'Select at least one application to mark printed.')
            return redirect('degree:bulk_mark_printed')

        apps = list(pending_apps.filter(pk__in=selected_ids))
        updated = 0
        skipped = []
        with transaction.atomic():
            for app in apps:
                serial = (request.POST.get(f'degree_serial_no_{app.pk}') or '').strip()
                book = (request.POST.get(f'degree_book_no_{app.pk}') or '').strip()
                if not serial or not book:
                    skipped.append(f'{app.tracking_no}: book no and sheet serial no are required')
                    continue
                duplicate = DegreeApplication.objects.filter(degree_serial_no=serial).exclude(pk=app.pk).exists()
                if duplicate:
                    skipped.append(f'{app.tracking_no}: sheet serial no {serial} already exists')
                    continue
                old = app.status
                app.degree_serial_no = serial
                app.degree_book_no = book
                app.status = ApplicationStatus.PRINTED_PENDING_SIGNATURE
                app.printed_by = request.user
                app.printed_at = timezone.now()
                app.save(update_fields=['degree_serial_no', 'degree_book_no', 'status', 'printed_by', 'printed_at', 'updated_at'])
                log_status(app, request.user, old, app.status, 'Bulk print details saved; status changed to Printed.')
                updated += 1

        if updated:
            messages.success(request, f'{updated} application(s) marked as Printed.')
        if skipped:
            messages.warning(request, 'Skipped: ' + '; '.join(skipped[:8]) + (' ...' if len(skipped) > 8 else ''))
        return redirect('degree:bulk_mark_printed')

    return render(request, 'degree/bulk_print_detail_form.html', {'applications': pending_apps})


def get_available_vc_applications():
    """Applications eligible for a new VC file.

    An application can belong to only one VCFileItem, so exclude anything
    already attached to a VC file. This prevents duplicate submission and the
    database UNIQUE constraint error on VCFileItem.application_id.
    """
    return DegreeApplication.objects.filter(
        status=ApplicationStatus.PRINTED_PENDING_SIGNATURE,
        vc_file_item__isnull=True,
    ).select_related('campus', 'department', 'program').order_by('tracking_no')


@role_required(UserProfile.Role.DESK)
def vc_file_list(request):
    files = VCFile.objects.select_related('created_by').annotate(
        applications_count=Count('items')
    ).order_by('-created_at')
    available_count = get_available_vc_applications().count()
    return render(request, 'degree/vc_file_list.html', {
        'files': files,
        'available_count': available_count,
    })


@role_required(UserProfile.Role.DESK)
def vc_file_create(request):
    available_apps = get_available_vc_applications()

    form = VCFileCreateForm(request.POST or None)
    form.fields['applications'].queryset = available_apps
    selected_app_ids = set(request.POST.getlist('applications')) if request.method == 'POST' else set()

    if request.method == 'POST' and form.is_valid():
        apps = list(form.cleaned_data['applications'])
        if not apps:
            form.add_error('applications', 'Select at least one available application.')
        else:
            # Re-check inside the transaction in case another user created a VC file
            # with one of these applications after this page loaded.
            selected_ids = [app.pk for app in apps]
            fresh_apps = list(get_available_vc_applications().filter(pk__in=selected_ids))
            unavailable_count = len(selected_ids) - len(fresh_apps)
            if unavailable_count:
                messages.warning(request, 'One or more selected applications are already linked to a VC file and were not added again.')
            if not fresh_apps:
                form.add_error('applications', 'Selected application is already linked to a VC file. Open VC Files to view it.')
            else:
                with transaction.atomic():
                    vc_file = VCFile.objects.create(created_by=request.user, remarks=form.cleaned_data.get('remarks', ''))
                    for idx, app in enumerate(fresh_apps, start=1):
                        VCFileItem.objects.create(vc_file=vc_file, application=app, serial_no=idx)
                        old = app.status
                        app.status = ApplicationStatus.VC_FILE
                        app.save(update_fields=['status', 'updated_at'])
                        log_status(app, request.user, old, app.status, f'Added to VC file {vc_file.file_no}.')
                messages.success(request, f'VC file {vc_file.file_no} created with {len(fresh_apps)} application(s).')
                return redirect('degree:vc_file_detail', pk=vc_file.pk)

    return render(request, 'degree/vc_file_form.html', {
        'form': form,
        'available_apps': available_apps,
        'selected_app_ids': selected_app_ids,
    })


@role_required(UserProfile.Role.DESK)
def vc_file_detail(request, pk):
    vc_file = get_object_or_404(
        VCFile.objects.select_related('created_by').prefetch_related(
            'items__application__campus', 'items__application__department', 'items__application__program'
        ),
        pk=pk,
    )
    return render(request, 'degree/vc_file_detail.html', {'vc_file': vc_file})


@role_required(UserProfile.Role.DESK)
def vc_file_edit(request, pk):
    vc_file = get_object_or_404(
        VCFile.objects.prefetch_related('items__application__campus', 'items__application__department', 'items__application__program'),
        pk=pk,
        status=VCFile.Status.DRAFT,
    )
    current_apps = DegreeApplication.objects.filter(vc_file_item__vc_file=vc_file).select_related('campus', 'department', 'program')
    available_apps = DegreeApplication.objects.filter(
        Q(vc_file_item__isnull=True, status=ApplicationStatus.PRINTED_PENDING_SIGNATURE) |
        Q(vc_file_item__vc_file=vc_file, status=ApplicationStatus.VC_FILE),
    ).select_related('campus', 'department', 'program').order_by('tracking_no')

    form = VCFileCreateForm(request.POST or None)
    form.fields['applications'].queryset = available_apps
    if request.method != 'POST':
        form.fields['applications'].initial = current_apps
        form.fields['remarks'].initial = vc_file.remarks
    selected_app_ids = set(request.POST.getlist('applications')) if request.method == 'POST' else set(str(app.pk) for app in current_apps)

    if request.method == 'POST' and form.is_valid():
        apps = list(form.cleaned_data['applications'])
        if not apps:
            form.add_error('applications', 'A draft VC file must contain at least one application.')
        else:
            selected_ids = [app.pk for app in apps]
            still_available = DegreeApplication.objects.filter(
                Q(vc_file_item__isnull=True, status=ApplicationStatus.PRINTED_PENDING_SIGNATURE) |
                Q(vc_file_item__vc_file=vc_file, status=ApplicationStatus.VC_FILE),
                pk__in=selected_ids,
            )
            apps = list(still_available.select_related('campus', 'department', 'program').order_by('tracking_no'))
            if len(apps) != len(selected_ids):
                form.add_error('applications', 'One or more selected applications are no longer available for this draft file.')
            else:
                with transaction.atomic():
                    old_apps = list(DegreeApplication.objects.filter(vc_file_item__vc_file=vc_file))
                    new_ids = {app.pk for app in apps}
                    for old_app in old_apps:
                        if old_app.pk not in new_ids and old_app.status == ApplicationStatus.VC_FILE:
                            old_status = old_app.status
                            old_app.status = ApplicationStatus.PRINTED_PENDING_SIGNATURE
                            old_app.save(update_fields=['status', 'updated_at'])
                            log_status(old_app, request.user, old_status, old_app.status, f'Removed from draft VC file {vc_file.file_no}.')
                    vc_file.remarks = form.cleaned_data.get('remarks', '')
                    vc_file.save(update_fields=['remarks'])
                    VCFileItem.objects.filter(vc_file=vc_file).delete()
                    for idx, app in enumerate(apps, start=1):
                        VCFileItem.objects.create(vc_file=vc_file, application=app, serial_no=idx)
                        if app.status != ApplicationStatus.VC_FILE:
                            old_status = app.status
                            app.status = ApplicationStatus.VC_FILE
                            app.save(update_fields=['status', 'updated_at'])
                            log_status(app, request.user, old_status, app.status, f'Added to VC file {vc_file.file_no}.')
                messages.success(request, f'VC file {vc_file.file_no} updated successfully.')
                return redirect('degree:vc_file_detail', pk=vc_file.pk)

    return render(request, 'degree/vc_file_form.html', {
        'form': form,
        'available_apps': available_apps,
        'selected_app_ids': selected_app_ids,
        'vc_file': vc_file,
        'is_edit': True,
    })


@role_required(UserProfile.Role.DESK)
def submit_vc_file(request, pk):
    vc_file = get_object_or_404(VCFile, pk=pk, status=VCFile.Status.DRAFT)
    with transaction.atomic():
        vc_file.status = VCFile.Status.SUBMITTED
        vc_file.submitted_at = timezone.now()
        vc_file.save(update_fields=['status', 'submitted_at'])
    messages.success(request, 'VC file submitted. Applications remain in VC File status until the file is received back.')
    return redirect('degree:vc_file_detail', pk=vc_file.pk)


@role_required(UserProfile.Role.DESK)
def return_vc_file(request, pk):
    vc_file = get_object_or_404(VCFile, pk=pk, status=VCFile.Status.SUBMITTED)
    with transaction.atomic():
        vc_file.status = VCFile.Status.RETURNED
        vc_file.returned_at = timezone.now()
        vc_file.save()
        for item in vc_file.items.select_related('application'):
            app = item.application
            old = app.status
            app.status = ApplicationStatus.READY_FOR_COLLECTION
            app.save(update_fields=['status', 'updated_at'])
            log_status(app, request.user, old, app.status, f'VC file {vc_file.file_no} received.')
    messages.success(request, 'VC file received and applications marked Ready for Collection.')
    return redirect('degree:vc_file_detail', pk=vc_file.pk)


@role_required(UserProfile.Role.DESK)
def deliver_application(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk, status=ApplicationStatus.READY_FOR_COLLECTION)
    form = DeliveryForm(request.POST or None, instance=app)
    if request.method == 'POST' and form.is_valid():
        old = app.status
        app = form.save(commit=False)
        app.status = ApplicationStatus.DELIVERED
        app.delivered_at = timezone.now()
        app.save()
        log_status(app, request.user, old, app.status, 'Degree delivered.')
        messages.success(request, 'Degree delivered.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/delivery_form.html', {'app': app, 'form': form})


@role_required(UserProfile.Role.ADMIN)
def cancel_application(request, pk):
    app = get_object_or_404(DegreeApplication, pk=pk)
    if app.status == ApplicationStatus.CANCELLED:
        messages.info(request, 'This application is already cancelled.')
        return redirect('degree:detail', pk=app.pk)
    if app.status == ApplicationStatus.DELIVERED:
        messages.error(request, 'A delivered degree cannot be cancelled.')
        return redirect('degree:detail', pk=app.pk)
    form = StatusRemarksForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        old = app.status
        app.status = ApplicationStatus.CANCELLED
        app.save(update_fields=['status', 'updated_at'])
        log_status(app, request.user, old, app.status, form.cleaned_data.get('remarks', 'Cancelled by admin.'))
        messages.success(request, 'Application cancelled.')
        return redirect('degree:detail', pk=app.pk)
    return render(request, 'degree/simple_action.html', {'app': app, 'form': form, 'title': 'Cancel Application'})


@login_required
def export_applications(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Applications'
    ws.append(['Tracking No', 'Name', 'Father Name', 'CNIC', 'Email', 'Registration No', 'Roll No', 'Campus', 'Department', 'Program', 'Type', 'Status', 'Created'])
    for app in DegreeApplication.objects.select_related('campus', 'department', 'program').all():
        ws.append([app.tracking_no, app.student_name, app.father_name, format_cnic_for_display(app.cnic), app.email, app.registration_no, app.roll_no, app.campus.name if app.campus else '', app.department.name if app.department else '', app.program.name, app.get_application_type_display(), app.get_status_display(), app.created_at.strftime('%Y-%m-%d')])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=degree_applications.xlsx'
    wb.save(response)
    return response
