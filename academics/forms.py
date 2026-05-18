from django import forms
from .models import Bank, Institute, Program, CourierCompany


class InstituteForm(forms.ModelForm):
    class Meta:
        model = Institute
        fields = ['name', 'category', 'is_active']


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



class InstituteExcelUploadForm(forms.Form):
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
