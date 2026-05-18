from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('institutes/', views.institute_list, name='institutes'),
    path('institutes/new/', views.institute_create, name='institute_create'),
    path('institutes/<int:pk>/edit/', views.institute_edit, name='institute_edit'),
    path('institutes/<int:pk>/delete/', views.institute_delete, name='institute_delete'),
    path('institutes/template/', views.institute_template_download, name='institute_template_download'),
    path('institutes/upload/', views.institute_upload_excel, name='institute_upload_excel'),

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
