from django.contrib import admin
from .models import Bank, Campus, Department, Program, CourierCompany


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'campus', 'is_active')
    list_filter = ('campus', 'is_active')
    search_fields = ('name', 'campus__name')


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'is_active')
    list_filter = ('level', 'is_active')
    search_fields = ('name',)


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(CourierCompany)
class CourierCompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
