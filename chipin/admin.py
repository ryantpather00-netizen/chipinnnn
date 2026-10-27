from django.contrib import admin
from .models import Group, Invite

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "admin")

@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("group", "invited_user", "invited_by", "accepted", "expires_at", "created_at")
    list_filter = ("accepted", "group")
    search_fields = ("group__name", "invited_user__username", "invited_by__username")