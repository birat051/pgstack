from django.contrib.postgres.search import SearchVectorField
from django.db import models


class TodoStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    DONE = 'done', 'Done'
    OVERDUE = 'overdue', 'Overdue'


class Todo(models.Model):
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=TodoStatus.choices,
        default=TodoStatus.PENDING,
    )
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    search_vector = SearchVectorField(null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.title


class JobStatus(models.TextChoices):
    QUEUED = 'queued', 'Queued'
    PROCESSING = 'processing', 'Processing'
    DONE = 'done', 'Done'
    FAILED = 'failed', 'Failed'


class Job(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE)
    job_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=12,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at'], name='job_status_created_idx'),
        ]
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.job_type} ({self.get_status_display()})'
