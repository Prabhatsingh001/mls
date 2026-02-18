"""
Celery configuration module for URL.ly asynchronous task processing.

This module sets up the Celery instance for handling background tasks in the URL.ly application.
It configures:
- Django settings integration
- Automatic task discovery from installed apps
- Celery namespace settings to avoid conflicts

The Celery instance is used for tasks like:
- Email sending
- Background data processing
- Scheduled maintenance tasks
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mls.settings")
app = Celery("mls")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
