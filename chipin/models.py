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


class GroupJoinRequest(models.Model):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    STATUSES = [(PENDING, 'Pending'), (APPROVED, 'Approved'), (REJECTED, 'Rejected')]

    group = models.ForeignKey(Group, related_name='join_requests', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='join_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['group', 'user'], name='unique_group_join_request')]
        ordering = ['-created_at']


class JoinRequestVote(models.Model):
    join_request = models.ForeignKey(GroupJoinRequest, related_name='votes', on_delete=models.CASCADE)
    voter = models.ForeignKey(User, related_name='join_request_votes', on_delete=models.CASCADE)
    approve = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['join_request', 'voter'], name='unique_join_request_vote')]


class Comment(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.content[:30]


class Event(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        ACTIVE = 'Active', 'Active'
        ARCHIVED = 'Archived', 'Archived'

    name = models.CharField(max_length=100)
    date = models.DateField()
    total_spend = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    archived_at = models.DateTimeField(null=True, blank=True)
    group = models.ForeignKey(Group, related_name='events', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='event_memberships', blank=True)

    def calculate_share(self):
        members_count = self.group.members.count()
        if members_count == 0:
            return 0
        return self.total_spend / members_count

    def check_status(self):
        share = self.calculate_share()
        for member in self.group.members.all():
            if member.profile.max_spend < share:
                self.status = self.Status.PENDING
                return False
        self.status = self.Status.ACTIVE
        return True

    def __str__(self):
        return self.name
