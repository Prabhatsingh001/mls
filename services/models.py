from django.db import models
from django.conf import settings


class Category(models.Model):
    """E.g., Plumbing, Electrical, HVAC, New Construction"""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, help_text="Used for SEO-friendly URLs")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Service(models.Model):
    """Specific jobs like 'Full House Wiring' or 'Motor Repair'"""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="services"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Standard rate for this job"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.category.name} - {self.title}"


class JobRequest(models.Model):
    """The initial inquiry from a customer"""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_requests"
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="job_requests"
    )
    description = models.TextField(help_text="Details of the repair or new work")
    site_address = models.TextField()
    preferred_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Track the lead status
    is_reviewed = models.BooleanField(default=False)
    is_converted_to_project = models.BooleanField(default=False)

    def __str__(self):
        return f"Request: {self.service.title} by {self.customer.full_name}"


class Project(models.Model):
    """The actual ongoing contract work"""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending/Quoted"
        SCHEDULED = "SCHED", "Scheduled"
        ONGOING = "ONGOING", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    # Link back to the original inquiry
    job_request = models.OneToOneField(
        JobRequest, on_delete=models.CASCADE, related_name="project"
    )

    # Assignment
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": "TECH"},
        related_name="assigned_projects",
    )

    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING
    )
    quoted_amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Internal notes for technicians")

    def get_status_display(self):
        return self.status

    def __str__(self):
        return f"PRJ-{self.pk}: {self.job_request.service.title}"
