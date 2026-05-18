from django.urls import path
from . import views

app_name = 'degree'

urlpatterns = [
    path('applications/', views.application_list, name='list'),
    path('applications/processing/', views.application_processing, name='processing'),
    path('fees/', views.fee_structure_list, name='fee_structures'),
    path('fees/new/', views.fee_structure_create, name='fee_structure_create'),
    path('fees/<int:pk>/edit/', views.fee_structure_edit, name='fee_structure_edit'),
    path('applications/new/', views.application_create, name='create'),
    path('applications/get-fee/', views.get_application_fee, name='get_application_fee'),
    path('applications/export/', views.export_applications, name='export'),
    path('applications/<int:pk>/', views.application_detail, name='detail'),
    path('applications/<int:pk>/edit/', views.application_edit, name='edit'),
    path('applications/<int:pk>/delete/', views.application_delete, name='delete'),
    path('applications/<int:pk>/receipt/', views.receipt, name='receipt'),
    path('applications/<int:pk>/documents/', views.update_documents, name='update_documents'),
    path('applications/<int:pk>/verify/', views.verify_application, name='verify'),
    path('applications/<int:pk>/send-for-printing/', views.send_for_printing, name='send_for_printing'),
    path('applications/<int:pk>/receive-for-print/', views.receive_for_print, name='receive_for_print'),
    path('applications/<int:pk>/mark-printed/', views.mark_printed, name='mark_printed'),
    path('applications/print-details/', views.bulk_mark_printed, name='bulk_mark_printed'),
    path('applications/<int:pk>/deliver/', views.deliver_application, name='deliver'),
    path('applications/<int:pk>/cancel/', views.cancel_application, name='cancel'),
    path('vc-files/', views.vc_file_list, name='vc_file_list'),
    path('vc-files/new/', views.vc_file_create, name='vc_file_create'),
    path('vc-files/<int:pk>/', views.vc_file_detail, name='vc_file_detail'),
    path('vc-files/<int:pk>/edit/', views.vc_file_edit, name='vc_file_edit'),
    path('vc-files/<int:pk>/submit/', views.submit_vc_file, name='vc_file_submit'),
    path('vc-files/<int:pk>/return/', views.return_vc_file, name='vc_file_return'),
]
