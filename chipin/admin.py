from django.contrib import admin
from .models import Group, Invite, GroupJoinRequest, JoinRequestVote, Comment


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'admin')


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ('group', 'invited_user', 'invited_by', 'accepted', 'expires_at', 'created_at')
    list_filter = ('accepted', 'group')
    search_fields = ('group__name', 'invited_user__username', 'invited_by__username')


@admin.register(GroupJoinRequest)
class GroupJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('group', 'user', 'status', 'created_at', 'reviewed_at')
    list_filter = ('status', 'group')


@admin.register(JoinRequestVote)
class JoinRequestVoteAdmin(admin.ModelAdmin):
    list_display = ('join_request', 'voter', 'approve', 'created_at')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('group', 'author', 'created_at', 'updated_at')
    list_filter = ('group', 'created_at')
    search_fields = ('content', 'group__name', 'author__username')
