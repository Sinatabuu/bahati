from django.db import models
from django.utils import timezone
from .middleware import get_current_user

class AuditedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "auth.User", null=True, blank=True, related_name="%(class)s_created",
        on_delete=models.SET_NULL, editable=False
    )
    updated_by = models.ForeignKey(
        "auth.User", null=True, blank=True, related_name="%(class)s_updated",
        on_delete=models.SET_NULL, editable=False
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        if not self.pk and not self.created_by:
            self.created_by = user
        self.updated_by = user
        super().save(*args, **kwargs)
