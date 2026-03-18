from django.db import models
from authentication.models import User
from services.models import Project

# Create your models here.
class Feedback(models.Model):
    class Rating(models.IntegerChoices):
        ONE = 1, "1 - Very Poor"
        TWO = 2, "2 - Poor"
        THREE = 3, "3 - Average"
        FOUR = 4, "4 - Good"
        FIVE = 5, "5 - Excellent"

    customer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="feedbacks"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="feedbacks"
    )
    rating = models.IntegerField(choices=Rating.choices)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback by {self.customer.full_name} for Project {self.project.pk}"