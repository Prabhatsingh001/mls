from django.conf import settings
from django.db import models


class Category(models.Model):
    """E.g., Plumbing, Electrical, HVAC, New Construction"""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, help_text="Used for SEO-friendly URLs")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "-")
        super().save(*args, **kwargs)


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


class ServiceItem(models.Model):
    class ItemType(models.TextChoices):
        TASK = "Task", "Task"
        MATERIAL = "Material", "Material"
        TOOL = "Tool", "Tool"

    name = models.CharField(max_length=200)
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    image = models.ImageField(upload_to="service_items/", null=True, blank=True)
    description = models.TextField(blank=True)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ServiceItemMapping(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="included_items"
    )
    item = models.ForeignKey(
        ServiceItem, on_delete=models.CASCADE, related_name="services_included"
    )
    quantity = models.PositiveIntegerField(default=1)
    is_optional = models.BooleanField(
        default=False, help_text="Whether this item is optional for the service"
    )

    extra_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Additional cost for this item beyond the base price of the service",
    )

    display_order = models.PositiveIntegerField(
        default=0, help_text="Order of items when displaying service details"
    )

    class Meta:
        unique_together = ("service", "item")
        ordering = ["display_order"]

    def __str__(self):
        return f"{self.quantity} x {self.item.name} for {self.service.title}"


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
    is_project_completed = models.BooleanField(default=False)

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


class ProjectExtraMaterial(models.Model):
    """Additional materials requested by technician during project execution."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="extra_materials"
    )
    catalog_item = models.ForeignKey(
        ServiceItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_extra_materials",
        limit_choices_to={"item_type": ServiceItem.ItemType.MATERIAL},
    )
    material_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    notes = models.CharField(max_length=255, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_extra_materials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.catalog_item:
            if not self.material_name:
                self.material_name = self.catalog_item.name
            if self.unit_cost is None:
                self.unit_cost = self.catalog_item.unit_cost
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        if self.unit_cost is None:
            return None
        return self.quantity * self.unit_cost

    def __str__(self):
        return f"Extra material for PRJ-{self.project_id}: {self.material_name}"
