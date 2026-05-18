from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from degree.permissions import role_required
from accounts.models import UserProfile
from .forms import BankForm, InstituteExcelUploadForm, InstituteForm, ProgramExcelUploadForm, ProgramForm, CourierCompanyForm
from .models import Bank, Institute, Program, CourierCompany


INSTITUTE_TEMPLATE_HEADERS = ['Name', 'Category', 'Active']
PROGRAM_TEMPLATE_HEADERS = ['Name', 'Level', 'Active']


def _delete_setup_item(request, model_class, object_name, redirect_url):
    item = get_object_or_404(model_class, pk=request.resolver_match.kwargs['pk'])
    if request.method == 'POST':
        try:
            item.delete()
            messages.success(request, f'{object_name} deleted successfully.')
        except ProtectedError:
            messages.error(request, f'This {object_name.lower()} cannot be deleted because it is already used in application/payment records. You can edit it and set Active = False instead.')
        return redirect(redirect_url)
    return render(request, 'academics/delete_confirm.html', {
        'item': item,
        'title': f'Delete {object_name}',
        'object_name': object_name,
        'cancel_url': redirect_url,
    })


def _normalize_institute_category(value):
    """Accept either category code or display name from Excel."""
    text = str(value or '').strip()
    if not text:
        return None
    upper_text = text.upper()
    for code, label in Institute.Category.choices:
        if upper_text == code.upper() or upper_text == label.upper():
            return code
    return None


def _normalize_program_level(value):
    """Accept either program level code or display name from Excel."""
    text = str(value or '').strip()
    if not text:
        return None
    upper_text = text.upper()
    for code, label in Program.Level.choices:
        if upper_text == code.upper() or upper_text == label.upper():
            return code
    return None


def _normalize_active(value):
    """Convert common Excel values to True/False."""
    if value is None or str(value).strip() == '':
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'true', 'yes', 'y', '1', 'active'}:
        return True
    if text in {'false', 'no', 'n', '0', 'inactive'}:
        return False
    return True


@role_required(UserProfile.Role.ADMIN)
def institute_template_download(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Institutes'

    ws.append(INSTITUTE_TEMPLATE_HEADERS)
    ws.append(['Department of Example Science', 'University Teaching Department', 'TRUE'])
    ws.append(['Example Government College', 'Government Affiliated College', 'TRUE'])
    ws.append(['Example Private College', 'Private Affiliated College', 'TRUE'])

    ws['E1'] = 'Allowed Categories'
    for row_no, (_, label) in enumerate(Institute.Category.choices, start=2):
        ws[f'E{row_no}'] = label

    ws['G1'] = 'Active values'
    ws['G2'] = 'TRUE'
    ws['G3'] = 'FALSE'

    column_widths = {
        'A': 38,
        'B': 34,
        'C': 14,
        'E': 34,
        'G': 16,
    }
    for column, width in column_widths.items():
        ws.column_dimensions[column].width = width

    for cell in ws[1]:
        cell.font = Font(bold=True)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="institute_upload_template.xlsx"'
    wb.save(response)
    return response


@role_required(UserProfile.Role.ADMIN)
def institute_upload_excel(request):
    if request.method != 'POST':
        return redirect('academics:institutes')

    form = InstituteExcelUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Please select a valid Excel file.')
        return redirect('academics:institutes')

    excel_file = form.cleaned_data['excel_file']
    try:
        workbook = load_workbook(excel_file, data_only=True)
        sheet = workbook.active
    except Exception:
        messages.error(request, 'The uploaded file could not be read. Please use the Excel template.')
        return redirect('academics:institutes')

    created = 0
    updated = 0
    skipped = 0
    errors = []

    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    for index, row in enumerate(rows, start=2):
        name = str(row[0] or '').strip() if len(row) > 0 else ''
        category_value = row[1] if len(row) > 1 else ''
        active_value = row[2] if len(row) > 2 else True

        if not name and not category_value and not active_value:
            continue

        if not name:
            skipped += 1
            errors.append(f'Row {index}: institute name is missing.')
            continue

        category = _normalize_institute_category(category_value)
        if not category:
            skipped += 1
            errors.append(f'Row {index}: invalid category "{category_value}".')
            continue

        _, was_created = Institute.objects.update_or_create(
            name=name,
            defaults={
                'category': category,
                'is_active': _normalize_active(active_value),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    if created or updated:
        messages.success(request, f'Excel upload complete. Created: {created}, Updated: {updated}, Skipped: {skipped}.')
    else:
        messages.warning(request, f'No institute was imported. Skipped: {skipped}.')

    if errors:
        preview = ' | '.join(errors[:5])
        more = f' More errors: {len(errors) - 5}.' if len(errors) > 5 else ''
        messages.warning(request, preview + more)

    return redirect('academics:institutes')


@login_required
def institute_list(request):
    return render(request, 'academics/institute_list.html', {'items': Institute.objects.all()})


@role_required(UserProfile.Role.ADMIN)
def institute_create(request):
    form = InstituteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Institute saved.')
        return redirect('academics:institutes')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Add Institute'})


@role_required(UserProfile.Role.ADMIN)
def institute_edit(request, pk):
    institute = get_object_or_404(Institute, pk=pk)
    form = InstituteForm(request.POST or None, instance=institute)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Institute updated.')
        return redirect('academics:institutes')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Edit Institute'})


@role_required(UserProfile.Role.ADMIN)
def institute_delete(request, pk):
    return _delete_setup_item(request, Institute, 'Institute', 'academics:institutes')


@role_required(UserProfile.Role.ADMIN)
def program_template_download(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Programs'

    ws.append(PROGRAM_TEMPLATE_HEADERS)
    ws.append(['BS Example Program', 'Bachelor', 'TRUE'])
    ws.append(['MS Example Program', 'Master', 'TRUE'])
    ws.append(['PhD Example Program', 'PhD', 'TRUE'])

    ws['E1'] = 'Allowed Levels'
    for row_no, (_, label) in enumerate(Program.Level.choices, start=2):
        ws[f'E{row_no}'] = label

    ws['G1'] = 'Active values'
    ws['G2'] = 'TRUE'
    ws['G3'] = 'FALSE'

    column_widths = {
        'A': 38,
        'B': 18,
        'C': 14,
        'E': 18,
        'G': 16,
    }
    for column, width in column_widths.items():
        ws.column_dimensions[column].width = width

    for cell in ws[1]:
        cell.font = Font(bold=True)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="program_upload_template.xlsx"'
    wb.save(response)
    return response


@role_required(UserProfile.Role.ADMIN)
def program_upload_excel(request):
    if request.method != 'POST':
        return redirect('academics:programs')

    form = ProgramExcelUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Please select a valid Excel file.')
        return redirect('academics:programs')

    excel_file = form.cleaned_data['excel_file']
    try:
        workbook = load_workbook(excel_file, data_only=True)
        sheet = workbook.active
    except Exception:
        messages.error(request, 'The uploaded file could not be read. Please use the Excel template.')
        return redirect('academics:programs')

    created = 0
    updated = 0
    skipped = 0
    errors = []

    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    for index, row in enumerate(rows, start=2):
        name = str(row[0] or '').strip() if len(row) > 0 else ''
        level_value = row[1] if len(row) > 1 else ''
        active_value = row[2] if len(row) > 2 else True

        if not name and not level_value and not active_value:
            continue

        if not name:
            skipped += 1
            errors.append(f'Row {index}: program name is missing.')
            continue

        level = _normalize_program_level(level_value)
        if not level:
            skipped += 1
            errors.append(f'Row {index}: invalid level "{level_value}".')
            continue

        _, was_created = Program.objects.update_or_create(
            name=name,
            defaults={
                'level': level,
                'is_active': _normalize_active(active_value),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    if created or updated:
        messages.success(request, f'Excel upload complete. Created: {created}, Updated: {updated}, Skipped: {skipped}.')
    else:
        messages.warning(request, f'No program was imported. Skipped: {skipped}.')

    if errors:
        preview = ' | '.join(errors[:5])
        more = f' More errors: {len(errors) - 5}.' if len(errors) > 5 else ''
        messages.warning(request, preview + more)

    return redirect('academics:programs')


@login_required
def program_list(request):
    return render(request, 'academics/program_list.html', {'items': Program.objects.all()})


@role_required(UserProfile.Role.ADMIN)
def program_create(request):
    form = ProgramForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Program saved.')
        return redirect('academics:programs')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Add Program'})


@role_required(UserProfile.Role.ADMIN)
def program_edit(request, pk):
    program = get_object_or_404(Program, pk=pk)
    form = ProgramForm(request.POST or None, instance=program)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Program updated.')
        return redirect('academics:programs')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Edit Program'})


@role_required(UserProfile.Role.ADMIN)
def program_delete(request, pk):
    return _delete_setup_item(request, Program, 'Program', 'academics:programs')


@login_required
def bank_list(request):
    return render(request, 'academics/bank_list.html', {'items': Bank.objects.all()})


@role_required(UserProfile.Role.ADMIN)
def bank_create(request):
    form = BankForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Bank saved.')
        return redirect('academics:banks')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Add Bank'})


@role_required(UserProfile.Role.ADMIN)
def bank_edit(request, pk):
    bank = get_object_or_404(Bank, pk=pk)
    form = BankForm(request.POST or None, instance=bank)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Bank updated.')
        return redirect('academics:banks')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Edit Bank'})


@role_required(UserProfile.Role.ADMIN)
def bank_delete(request, pk):
    return _delete_setup_item(request, Bank, 'Bank', 'academics:banks')



@login_required
def courier_list(request):
    return render(request, 'academics/courier_list.html', {'items': CourierCompany.objects.all()})


@role_required(UserProfile.Role.ADMIN)
def courier_create(request):
    form = CourierCompanyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Courier company saved.')
        return redirect('academics:couriers')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Add Courier Company'})


@role_required(UserProfile.Role.ADMIN)
def courier_edit(request, pk):
    company = get_object_or_404(CourierCompany, pk=pk)
    form = CourierCompanyForm(request.POST or None, instance=company)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Courier company updated.')
        return redirect('academics:couriers')
    return render(request, 'academics/form.html', {'form': form, 'title': 'Edit Courier Company'})


@role_required(UserProfile.Role.ADMIN)
def courier_delete(request, pk):
    return _delete_setup_item(request, CourierCompany, 'Courier Company', 'academics:couriers')
