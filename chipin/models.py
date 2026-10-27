import uuid
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

def default_invite_expiry():
    return timezone.now() + timedelta(days=14)

class Group(models.Model):
    name = models.CharField(max_length=100)
    admin = models.ForeignKey(User, related_name='admin_groups', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='group_memberships', blank=True)
    def __str__(self):
        return self.name

class Invite(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invites")
    invited_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_invites")
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_invites")
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_invite_expiry)
    def __str__(self):
        return f"Invite to '{self.group.name}' for {self.invited_user.username}"
    def is_expired(self):
        return timezone.now() > self.expires_at
    def accept_url(self):
        return settings.SITE_ORIGIN + reverse("chipin:accept_invite", args=[str(self.token)])
    @property
    def invitee_email(self):
        return (self.invited_user.email or "").strip()
