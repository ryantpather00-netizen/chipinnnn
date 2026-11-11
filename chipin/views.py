from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import GroupCreationForm, CommentForm
from .models import Group, GroupJoinRequest, Invite, JoinRequestVote, Comment


@login_required(login_url='users:login')
def home(request):
    groups = Group.objects.filter(Q(admin=request.user) | Q(members=request.user)).distinct()
    return render(request, 'chipin/home.html', {'groups': groups})


@login_required(login_url='users:login')
def create_group(request):
    if request.method == 'POST':
        form = GroupCreationForm(request.POST, user=request.user)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Group "{group.name}" created successfully!')
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = GroupCreationForm(user=request.user)
    return render(request, 'chipin/create_group.html', {'form': form})


@login_required(login_url='users:login')
def browse_groups(request):
    groups = Group.objects.all().order_by('name')
    joined_ids = set(Group.objects.filter(Q(admin=request.user) | Q(members=request.user)).values_list('id', flat=True))
    pending_ids = set(GroupJoinRequest.objects.filter(user=request.user, status=GroupJoinRequest.PENDING).values_list('group_id', flat=True))
    return render(request, 'chipin/browse_groups.html', {
        'groups': groups, 'joined_ids': joined_ids, 'pending_ids': pending_ids
    })


@login_required(login_url='users:login')
def group_detail(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    is_member = group.admin_id == request.user.id or group.members.filter(id=request.user.id).exists()
    my_join_request = GroupJoinRequest.objects.filter(group=group, user=request.user).first()
    comments = Comment.objects.filter(group=group).select_related('author__profile').order_by('created_at') if is_member else []
    if request.method == 'POST':
        if not is_member:
            messages.error(request, 'Only members can post comments.')
            return redirect('chipin:group_detail', group_id=group.id)
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.group = group
            comment.author = request.user
            comment.save()
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = CommentForm()
    return render(request, 'chipin/group_detail.html', {
        'group': group,
        'is_member': is_member,
        'is_admin': group.admin_id == request.user.id,
        'my_join_request': my_join_request,
        'comments': comments,
        'form': form,
    })


@login_required(login_url='users:login')
@require_POST
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.id == group.admin_id:
        group.delete()
        messages.success(request, 'Group deleted.')
        return redirect('chipin:home')
    messages.error(request, 'You do not have permission to delete this group.')
    return redirect('chipin:group_detail', group_id=group.id)


@login_required(login_url='users:login')
def invite_users(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.id != group.admin_id:
        messages.error(request, 'Only the group administrator can invite members.')
        return redirect('chipin:group_detail', group_id=group.id)

    users_not_in_group = User.objects.exclude(id__in=group.members.values_list('id', flat=True)).exclude(id=group.admin_id).select_related('profile')
    if request.method == 'POST':
        try:
            invited_user_id = int(request.POST.get('invited_user_id', '0'))
        except (TypeError, ValueError):
            invited_user_id = 0
        invited_user = users_not_in_group.filter(id=invited_user_id).first()
        if not invited_user:
            messages.error(request, 'Please select a valid user to invite.')
            return redirect('chipin:invite_users', group_id=group.id)

        invite, _ = Invite.objects.get_or_create(group=group, invited_user=invited_user, defaults={'invited_by': request.user})
        if invite.accepted or invite.is_expired():
            invite.token = __import__('uuid').uuid4()
            invite.expires_at = timezone.now() + timedelta(days=14)
            invite.accepted = False
            invite.invited_by = request.user
            invite.save(update_fields=['token', 'expires_at', 'accepted', 'invited_by'])
        return redirect('chipin:web3forms_invite', group_id=group.id, invite_id=invite.id)
    return render(request, 'chipin/invite_users.html', {'group': group, 'users_not_in_group': users_not_in_group})


@login_required(login_url='users:login')
def web3forms_invite(request, group_id, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, group_id=group_id)
    if request.user.id != invite.group.admin_id:
        messages.error(request, 'Only the group administrator can send invitations.')
        return redirect('chipin:group_detail', group_id=group_id)
    thank_you_url = request.build_absolute_uri(reverse('chipin:invite_sent') + f'?group={invite.group.id}&invite={invite.id}')
    return render(request, 'chipin/web3forms_invite.html', {
        'group': invite.group, 'invite': invite, 'accept_link': invite.accept_url(),
        'WEB3FORMS_ACCESS_KEY': getattr(settings, 'WEB3FORMS_ACCESS_KEY', ''),
        'redirect_url': thank_you_url,
    })


@login_required(login_url='users:login')
def accept_invite(request, token):
    invite = get_object_or_404(Invite.objects.select_related('group', 'invited_user'), token=token)
    if request.user.id != invite.invited_user_id:
        messages.error(request, 'This invitation belongs to another account. Please log in with the invited account.')
        return redirect('chipin:home')
    if request.method == 'GET':
        return render(request, 'chipin/confirm_invite.html', {'invite': invite})
    if request.method != 'POST':
        return redirect('chipin:home')
    with transaction.atomic():
        invite = Invite.objects.select_for_update().get(pk=invite.pk)
        if invite.accepted:
            messages.info(request, 'This invitation has already been used.')
        elif invite.is_expired():
            messages.error(request, 'This invitation has expired.')
            return redirect('chipin:home')
        else:
            invite.group.members.add(request.user)
            invite.accepted = True
            invite.save(update_fields=['accepted'])
            GroupJoinRequest.objects.filter(group=invite.group, user=request.user, status=GroupJoinRequest.PENDING).update(status=GroupJoinRequest.APPROVED, reviewed_at=timezone.now())
            messages.success(request, f'You have joined {invite.group.name}.')
    return redirect('chipin:group_detail', group_id=invite.group_id)


@login_required(login_url='users:login')
def invite_sent(request):
    group_id = request.GET.get('group')
    invite_id = request.GET.get('invite')
    group = Group.objects.filter(pk=group_id, admin=request.user).first() if group_id and group_id.isdigit() else None
    invite = Invite.objects.filter(pk=invite_id, group=group).first() if group and invite_id and invite_id.isdigit() else None
    return render(request, 'chipin/invite_sent.html', {'group': group, 'invite': invite})


@login_required(login_url='users:login')
@require_POST
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.id == group.admin_id:
        messages.error(request, 'Admins cannot leave their own group.')
    elif not group.members.filter(pk=request.user.id).exists():
        messages.error(request, 'You are not a member of this group.')
    else:
        group.members.remove(request.user)
        messages.success(request, f'You left "{group.name}".')
        return redirect('chipin:home')
    return redirect('chipin:group_detail', group_id=group.id)


@login_required(login_url='users:login')
@require_POST
def request_to_join(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if group.admin_id == request.user.id or group.members.filter(pk=request.user.id).exists():
        messages.info(request, 'You are already a member of this group.')
    else:
        join_request, created = GroupJoinRequest.objects.get_or_create(group=group, user=request.user)
        if not created and join_request.status == GroupJoinRequest.PENDING:
            messages.info(request, 'Your join request is already pending.')
        elif not created and join_request.status == GroupJoinRequest.APPROVED:
            messages.info(request, 'Your request was approved. Contact the group admin if you cannot access the group.')
        else:
            if not created:
                join_request.status = GroupJoinRequest.PENDING
                join_request.reviewed_at = None
                join_request.save(update_fields=['status', 'reviewed_at'])
                join_request.votes.all().delete()
            messages.success(request, 'Your join request has been sent.')
    return redirect('chipin:group_detail', group_id=group.id)


@login_required(login_url='users:login')
def group_join_requests(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if group.admin_id != request.user.id and not group.members.filter(pk=request.user.pk).exists():
        messages.error(request, 'Only group members can view join requests.')
        return redirect('chipin:group_detail', group_id=group.id)
    join_requests = list(GroupJoinRequest.objects.filter(group=group, status=GroupJoinRequest.PENDING).select_related('user__profile').prefetch_related('votes'))
    votes_by_request = {r.id: next((v for v in r.votes.all() if v.voter_id == request.user.pk), None) for r in join_requests}
    for jr in join_requests:
        jr.my_vote = votes_by_request[jr.id]
        jr.yes_count = sum(v.approve for v in jr.votes.all())
        jr.no_count = sum(not v.approve for v in jr.votes.all())
    return render(request, 'chipin/join_requests.html', {
        'group': group, 'join_requests': join_requests, 'is_admin': group.admin_id == request.user.id,
    })


def _resolve_votes(group, join_request):
    eligible_ids = set(group.members.values_list('pk', flat=True)) | {group.admin_id}
    votes = JoinRequestVote.objects.filter(join_request=join_request, voter_id__in=eligible_ids)
    approvals = votes.filter(approve=True).count()
    rejections = votes.filter(approve=False).count()
    threshold = len(eligible_ids) // 2 + 1
    if approvals >= threshold:
        join_request.status = GroupJoinRequest.APPROVED
        join_request.reviewed_at = timezone.now()
        join_request.save(update_fields=['status', 'reviewed_at'])
        group.members.add(join_request.user)
    elif rejections >= threshold:
        join_request.status = GroupJoinRequest.REJECTED
        join_request.reviewed_at = timezone.now()
        join_request.save(update_fields=['status', 'reviewed_at'])


@login_required(login_url='users:login')
@require_POST
def vote_join_request(request, group_id, request_id):
    with transaction.atomic():
        group = get_object_or_404(Group.objects.select_for_update(), pk=group_id)
        if group.admin_id != request.user.id and not group.members.filter(pk=request.user.pk).exists():
            messages.error(request, 'Only members can vote.')
            return redirect('chipin:group_detail', group_id=group_id)
        jr = get_object_or_404(GroupJoinRequest, pk=request_id, group=group)
        if jr.status != GroupJoinRequest.PENDING:
            messages.info(request, 'This request has already been resolved.')
        elif request.POST.get('vote') not in ('yes', 'no'):
            messages.error(request, 'Please select a valid vote.')
        else:
            JoinRequestVote.objects.update_or_create(join_request=jr, voter=request.user, defaults={'approve': request.POST['vote'] == 'yes'})
            _resolve_votes(group, jr)
            messages.success(request, 'Your vote has been recorded.')
    return redirect('chipin:group_join_requests', group_id=group_id)


@login_required(login_url='users:login')
@require_POST
def review_join_request(request, group_id, request_id):
    with transaction.atomic():
        group = get_object_or_404(Group.objects.select_for_update(), pk=group_id)
        if group.admin_id != request.user.id:
            messages.error(request, 'Only the group admin can decide requests directly.')
            return redirect('chipin:group_detail', group_id=group_id)
        jr = get_object_or_404(GroupJoinRequest, pk=request_id, group=group)
        if jr.status != GroupJoinRequest.PENDING:
            messages.info(request, 'This request is already resolved.')
        elif request.POST.get('decision') not in ('approve', 'reject'):
            messages.error(request, 'Invalid decision.')
        else:
            approved = request.POST['decision'] == 'approve'
            jr.status = GroupJoinRequest.APPROVED if approved else GroupJoinRequest.REJECTED
            jr.reviewed_at = timezone.now()
            jr.save(update_fields=['status', 'reviewed_at'])
            if approved:
                group.members.add(jr.user)
            messages.success(request, 'Join request approved.' if approved else 'Join request rejected.')
    return redirect('chipin:group_join_requests', group_id=group_id)



def _is_group_member(group, user):
    return group.admin_id == user.pk or group.members.filter(pk=user.pk).exists()


@login_required(login_url='users:login')
def group_chat(request, group_id):
    return redirect('chipin:group_detail', group_id=group_id)


@login_required(login_url='users:login')
@require_POST
def post_comment(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    if not _is_group_member(group, request.user):
        messages.error(request, 'Only group members can post messages.')
        return redirect('chipin:group_detail', group_id=group.pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.group = group
        comment.author = request.user
        comment.save()
        messages.success(request, 'Message posted.')
    else:
        messages.error(request, 'Message not saved: ' + ' '.join(form.errors.get('content', ['Invalid message.'])))
    return redirect('chipin:group_detail', group_id=group.pk)


@login_required(login_url='users:login')
def edit_comment(request, group_id, comment_id):
    group = get_object_or_404(Group, pk=group_id)
    if not _is_group_member(group, request.user):
        messages.error(request, 'Only group members can access this chat.')
        return redirect('chipin:group_detail', group_id=group.pk)
    comment = get_object_or_404(Comment, pk=comment_id, group=group)
    if comment.author_id != request.user.pk:
        messages.error(request, 'You can only edit your own messages.')
        return redirect('chipin:group_detail', group_id=group.pk)
    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            messages.success(request, 'Message updated.')
            return redirect('chipin:group_detail', group_id=group.pk)
    else:
        form = CommentForm(instance=comment)
    return render(request, 'chipin/edit_comment.html', {
        'group': group, 'comment': comment, 'form': form,
    })


@login_required(login_url='users:login')
@require_POST
def delete_comment(request, group_id, comment_id):
    group = get_object_or_404(Group, pk=group_id)
    if not _is_group_member(group, request.user):
        messages.error(request, 'Only group members can access this chat.')
        return redirect('chipin:group_detail', group_id=group.pk)
    comment = get_object_or_404(Comment, pk=comment_id, group=group)
    if comment.author_id != request.user.pk and group.admin_id != request.user.pk:
        messages.error(request, 'You cannot delete this message.')
    else:
        comment.delete()
        messages.success(request, 'Message deleted.')
    return redirect('chipin:group_detail', group_id=group.pk)


@login_required(login_url='users:login')
def my_invites(request):
    invites = Invite.objects.filter(invited_user=request.user, accepted=False).select_related('group', 'invited_by').order_by('-created_at')
    return render(request, 'chipin/my_invites.html', {'invites': invites})


@login_required(login_url='users:login')
@require_POST
def decline_invite(request, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, invited_user=request.user, accepted=False)
    invite.delete()
    messages.success(request, 'Invite declined.')
    return redirect('chipin:my_invites')
