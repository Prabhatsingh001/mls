from django.shortcuts import render
from .models import AuditLog


def get_log_details(request, log_id):
    log_entry = AuditLog.objects.get(id=log_id)
    return render(request, "log_details.html", {"log": log_entry})
