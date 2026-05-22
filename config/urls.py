from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from degree import views as degree_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', degree_views.public_tracking, name='track_application'),
    path('dashboard/', degree_views.dashboard, name='dashboard'),
    
    # FIX: Corrected template directory path here
    path('accounts/login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('academics/', include('academics.urls')),
    path('degree/', include('degree.urls'), name='degree_app'),
    path('reports/', include('reports.urls')),
]

