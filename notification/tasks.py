from celery import shared_task

from notification.models import Notification, PushSubscription
from notification.services import create_notification, notify_admins
from services.models import Project


@shared_task
def send_admin_sms_task(admin_ids, title, message):
    """Send SMS to all admins who have a phone number."""
    from authentication.models import User
    from notification.sms import send_sms

    admins = User.objects.filter(pk__in=admin_ids, phone_number__gt="")
    for admin in admins:
        send_sms(to=admin.phone_number, body=f"[MLS] {title}\n{message}")


@shared_task
def send_admin_push_task(admin_ids, title, message):
    """Send browser push notification to all admins with a push subscription."""
    from notification.push import send_push

    subs = PushSubscription.objects.filter(user_id__in=admin_ids)
    if subs.exists():
        send_push(subs, title, message)


@shared_task
def remind_pending_work():
    """
    Periodic task – runs daily.
    Creates reminder notifications for:
      • Admins – about unreviewed job requests and pending/scheduled projects.
      • Technicians – about their own pending/ongoing projects.
    """
    from services.models import JobRequest

    # ── Admin reminders ──────────────────────────────────────────────
    unreviewed_count = JobRequest.objects.filter(
        is_reviewed=False, is_converted_to_project=False
    ).count()

    pending_projects_count = Project.objects.filter(
        status__in=[Project.Status.PENDING, Project.Status.SCHEDULED]
    ).count()

    if unreviewed_count or pending_projects_count:
        parts = []
        if unreviewed_count:
            parts.append(f"{unreviewed_count} unreviewed request(s)")
        if pending_projects_count:
            parts.append(f"{pending_projects_count} pending/scheduled project(s)")

        notify_admins(
            type=Notification.Type.PENDING_REMINDER,
            title="Pending Work Reminder",
            message="You have " + " and ".join(parts) + " that need attention.",
        )

    # ── Technician reminders ─────────────────────────────────────────
    active_projects = Project.objects.filter(
        status__in=[
            Project.Status.PENDING,
            Project.Status.SCHEDULED,
            Project.Status.ONGOING,
        ],
        technician__isnull=False,
    ).select_related("technician", "job_request__service")

    # Group by technician to send one notification per tech
    tech_projects: dict[int, list[str]] = {}
    for project in active_projects:
        tid = project.technician_id  # type: ignore
        if tid is None:
            # Defensive check: should not happen due to technician__isnull=False filter
            continue
        label = f"PRJ-{project.pk} ({project.job_request.service.title})"
        tech_projects.setdefault(tid, []).append(label)

    for tech_id, labels in tech_projects.items():
        create_notification(
            user=None,
            user_id=tech_id,
            type=Notification.Type.PENDING_REMINDER,
            title="Pending Work Reminder",
            message=(
                f"You have {len(labels)} active project(s): "
                + ", ".join(labels[:5])
                + ("…" if len(labels) > 5 else "")
                + "."
            ),
        )

    return f"Reminders sent - {unreviewed_count} unreviewed, {pending_projects_count} pending projects."
