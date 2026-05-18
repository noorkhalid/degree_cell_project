from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from degree.models import DegreeApplication


@login_required
def reports_home(request):
    by_status = DegreeApplication.objects.values('status').annotate(total=Count('id'))
    by_type = DegreeApplication.objects.values('application_type').annotate(total=Count('id'))
    return render(request, 'reports/home.html', {'by_status': by_status, 'by_type': by_type})
