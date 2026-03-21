from celery import shared_task


@shared_task()
def record_audit_log_tasks(log_details):
    """
    Record an audit log entry asynchronously.

    Args:
        log_details: Dictionary containing details of the audit log such as
                     user_id, action, timestamp, ip_address, user_agent

    This task creates an AuditLog record in the database with the
    provided log details.
    """
    from .models import AuditLog

    AuditLog.objects.create(
        actor_id=log_details.get("actor"),
        category=log_details.get("category"),
        action=log_details.get("action"),
        description=log_details.get("description", ""),
        content_type_id=log_details.get("content_type_id"),
        object_id=log_details.get("object_id"),
        ip_address=log_details.get("ip_address"),
        metadata=log_details.get("metadata", {}),
    )
