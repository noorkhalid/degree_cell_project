from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('campuses/', views.campus_list, name='campuses'),
    path('campuses/new/', views.campus_create, name='campus_create'),
    path('campuses/<int:pk>/edit/', views.campus_edit, name='campus_edit'),
    path('campuses/<int:pk>/delete/', views.campus_delete, name='campus_delete'),
    path('campuses/template/', views.campus_template_download, name='campus_template_download'),
    path('campuses/upload/', views.campus_upload_excel, name='campus_upload_excel'),

    path('departments/', views.department_list, name='departments'),
    path('departments/new/', views.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    path('departments/template/', views.department_template_download, name='department_template_download'),
    path('departments/upload/', views.department_upload_excel, name='department_upload_excel'),
    path('departments/by-campus/', views.departments_by_campus, name='departments_by_campus'),

    path('programs/', views.program_list, name='programs'),
    path('programs/new/', views.program_create, name='program_create'),
    path('programs/<int:pk>/edit/', views.program_edit, name='program_edit'),
    path('programs/<int:pk>/delete/', views.program_delete, name='program_delete'),
    path('programs/template/', views.program_template_download, name='program_template_download'),
    path('programs/upload/', views.program_upload_excel, name='program_upload_excel'),

    path('banks/', views.bank_list, name='banks'),
    path('banks/new/', views.bank_create, name='bank_create'),
    path('banks/<int:pk>/edit/', views.bank_edit, name='bank_edit'),
    path('banks/<int:pk>/delete/', views.bank_delete, name='bank_delete'),

    path('couriers/', views.courier_list, name='couriers'),
    path('couriers/new/', views.courier_create, name='courier_create'),
    path('couriers/<int:pk>/edit/', views.courier_edit, name='courier_edit'),
    path('couriers/<int:pk>/delete/', views.courier_delete, name='courier_delete'),
]
