from django import forms
from .models import Bank, Campus, Department, Program, CourierCompany


class CampusForm(forms.ModelForm):
    class Meta:
        model = Campus
        fields = ['name', 'is_active']


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['campus', 'name', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = Campus.objects.filter(is_active=True)
        self.fields['campus'].empty_label = 'Select Campus'


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = ['name', 'level', 'is_active']


class BankForm(forms.ModelForm):
    class Meta:
        model = Bank
        fields = ['name', 'is_active']


class CourierCompanyForm(forms.ModelForm):
    class Meta:
        model = CourierCompany
        fields = ['name', 'is_active']


class CampusExcelUploadForm(forms.Form):
    excel_file = forms.FileField(label='Excel file')

    def clean_excel_file(self):
        excel_file = self.cleaned_data['excel_file']
        if not excel_file.name.lower().endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError('Please upload an .xlsx Excel file.')
        return excel_file


class DepartmentExcelUploadForm(forms.Form):
    excel_file = forms.FileField(label='Excel file')

    def clean_excel_file(self):
        excel_file = self.cleaned_data['excel_file']
        if not excel_file.name.lower().endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError('Please upload an .xlsx Excel file.')
        return excel_file


class ProgramExcelUploadForm(forms.Form):
    excel_file = forms.FileField(label='Excel file')

    def clean_excel_file(self):
        excel_file = self.cleaned_data['excel_file']
        if not excel_file.name.lower().endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError('Please upload an .xlsx Excel file.')
        return excel_file
