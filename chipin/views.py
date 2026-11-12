from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from .models import Group, Invite, GroupJoinRequest, JoinRequestVote, Comment, Event
from .forms import GroupCreationForm, CommentForm
from django.urls import reverse
from django.views.decorators.http import require_POST
import uuid

@login_required(login_url='users:login')
def home(request):
    return render(request, "chipin/home.html")

@login_required
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

@login_required
def group_detail(request, group_id, edit_comment_id=None):
    group = get_object_or_404(Group, id=group_id)
    is_member = request.user == group.admin or request.user in group.members.all()
    comments = group.comments.all().order_by('-created_at') if is_member else []
    my_join_request = GroupJoinRequest.objects.filter(group=group, user=request.user).first()

    comment_to_edit = None
    if edit_comment_id:
        comment_to_edit = get_object_or_404(Comment, id=edit_comment_id, group=group)
        if comment_to_edit.author != request.user or not is_member:
            return redirect('chipin:group_detail', group_id=group.id)

    if request.method == 'POST' and is_member:
        form = CommentForm(request.POST, instance=comment_to_edit)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.group = group
            comment.save()
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = CommentForm(instance=comment_to_edit)

    join_requests = group.join_requests.filter(status='pending') if is_member else []
    for jr in join_requests:
        jr.yes_count = jr.votes.filter(approve=True).count()
        jr.no_count = jr.votes.filter(approve=False).count()

    event_share_info = {}
    if is_member:
        for event in group.events.all():
            share = event.calculate_share()
            event_share_info[event] = {
                'share': share,
                'eligible': request.user.profile.max_spend >= share,
                'status': event.status,
                'joined': request.user in event.members.all(),
            }

    return render(request, 'chipin/group_detail.html', {
        'group': group,
        'is_member': is_member,
        'comments': comments,
        'form': form,
        'comment_to_edit': comment_to_edit,
        'my_join_request': my_join_request,
        'join_requests': join_requests,
        'event_share_info': event_share_info,
    })

@login_required
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user == group.admin:
        group.delete()
        messages.success(request, f'Group "{group.name}" has been deleted.')
    else:
        messages.error(request, "You do not have permission to delete this group.")
    return redirect('chipin:home')

@login_required
def invite_users(request, group_id):
    group = get_object_or_404(Group, id=group_id)


    if request.user != group.admin:
        messages.error(request, "Only the group administrator can invite members.")
        return redirect("chipin:group_detail", group_id=group.id)


    users_not_in_group = User.objects.exclude(
        id__in=group.members.values_list('id', flat=True)
    )

    if request.method == "POST":
        try:
            invited_user_id = int(request.POST.get("invited_user_id", "0"))
        except ValueError:
            invited_user_id = 0

        invited_user = users_not_in_group.filter(id=invited_user_id).first()
        if not invited_user:
            messages.error(request, "Please select a valid user to invite.")
            return redirect("chipin:invite_users", group_id=group.id)

        invite, created = Invite.objects.get_or_create(
            group=group,
            invited_user=invited_user,
            defaults={"invited_by": request.user},
        )
        if invite.accepted or invite.is_expired():
            invite.token = uuid.uuid4()
            invite.expires_at = timezone.now() + timezone.timedelta(days=14)
            invite.accepted = False
            invite.save()

        return redirect("chipin:web3forms_invite", group_id=group.id, invite_id=invite.id)

    return render(
        request,
        "chipin/invite_users.html",
        {"group": group, "users_not_in_group": users_not_in_group},
    )

@login_required
def web3forms_invite(request, group_id, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, group_id=group_id)
    if request.user != invite.group.admin:
        return redirect('chipin:home')
    accept_link = invite.accept_url()
    WEB3FORMS_ACCESS_KEY = getattr(settings, "WEB3FORMS_ACCESS_KEY", "")

    thank_you_url = request.build_absolute_uri(
            reverse("chipin:invite_sent") + f"?group={invite.group.id}&invite={invite.id}"
        )

    return render(
        request,
        "chipin/web3forms_invite.html",
        {
            "group": invite.group,
            "invite": invite,
            "accept_link": accept_link,
            "WEB3FORMS_ACCESS_KEY": WEB3FORMS_ACCESS_KEY,
            "redirect_url": thank_you_url,
        },
    )

@login_required
def accept_invite(request, token):
    invite = get_object_or_404(Invite, token=token)
    if request.user != invite.invited_user:
        messages.error(request, 'This invitation is for another user.')
        return redirect('chipin:my_invites')
    if invite.accepted:
        if getattr(settings, "DEMO_AUTO_ACCEPT_INVITES", False):
            _auto_login_as_invitee(request, invite)
        messages.info(request, f"This invitation has already been used for {invite.invited_user.username}.")
        return redirect("chipin:group_detail", group_id=invite.group.id)
    if hasattr(invite, "is_expired") and invite.is_expired():
        messages.error(request, "This invitation has expired.")
        return redirect("chipin:home")
    if getattr(settings, "DEMO_AUTO_ACCEPT_INVITES", False):
        _auto_login_as_invitee(request, invite)
    group = invite.group
    group.members.add(invite.invited_user)
    invite.accepted = True
    if not hasattr(invite, "used_at"):
        pass
    else:
        invite.used_at = timezone.now()
    invite.save()
    messages.success(request, f"You have joined {group.name}.")
    return redirect("chipin:group_detail", group_id=group.id)

def _auto_login_as_invitee(request, invite):
    user = invite.invited_user
    backend = None
    try:
        backend = settings.AUTHENTICATION_BACKENDS[0]
    except Exception:
        backend = "django.contrib.auth.backends.ModelBackend"
    setattr(user, "backend", backend)
    login(request, user)

@login_required
def invite_sent(request):
    group_id = request.GET.get("group")
    invite_id = request.GET.get("invite")
    group = get_object_or_404(Group, id=group_id) if group_id else None
    invite = get_object_or_404(Invite, id=invite_id) if invite_id else None
    return render(
        request,
        "chipin/invite_sent.html",
        {
            "group": group,
            "invite": invite,
        },
    )

@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if request.user not in group.members.all():
        messages.error(request, "You’re not a member of this group.")
        return redirect("chipin:group_detail", group_id=group.id)

    if request.user == group.admin:
        messages.error(request, "Admins can’t leave their own group. Transfer admin or delete the group.")
        return redirect("chipin:group_detail", group_id=group.id)

    group.members.remove(request.user)
    messages.success(request, f'You left "{group.name}".')
    return redirect("chipin:home")


@login_required
def browse_groups(request):
    groups = Group.objects.all().order_by('name')
    joined_ids = list(request.user.group_memberships.values_list('id', flat=True))
    pending_ids = list(GroupJoinRequest.objects.filter(user=request.user, status='pending').values_list('group_id', flat=True))
    return render(request, 'chipin/browse_groups.html', {'groups': groups, 'joined_ids': joined_ids, 'pending_ids': pending_ids})

@login_required
def my_invites(request):
    invites = Invite.objects.filter(invited_user=request.user, accepted=False).order_by('-created_at')
    return render(request, 'chipin/my_invites.html', {'invites': invites})

@login_required
@require_POST
def decline_invite(request, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, invited_user=request.user, accepted=False)
    invite.delete()
    return redirect('chipin:my_invites')

@login_required
@require_POST
def request_to_join(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin and request.user not in group.members.all():
        jr, created = GroupJoinRequest.objects.get_or_create(group=group, user=request.user)
        if not created and jr.status != 'pending':
            jr.status = 'pending'
            jr.reviewed_at = None
            jr.save()
            jr.votes.all().delete()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def vote_join_request(request, group_id, request_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin and request.user not in group.members.all():
        return redirect('chipin:home')
    jr = get_object_or_404(GroupJoinRequest, id=request_id, group=group, status='pending')
    if request.POST.get('vote') in ['yes', 'no']:
        JoinRequestVote.objects.update_or_create(join_request=jr, voter=request.user, defaults={'approve': request.POST['vote'] == 'yes'})
        yes_votes = jr.votes.filter(approve=True).count()
        no_votes = jr.votes.filter(approve=False).count()
        needed = group.members.count() // 2 + 1
        if yes_votes >= needed:
            jr.status = 'approved'
            jr.reviewed_at = timezone.now()
            jr.save()
            group.members.add(jr.user)
        elif no_votes >= needed:
            jr.status = 'rejected'
            jr.reviewed_at = timezone.now()
            jr.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def review_join_request(request, group_id, request_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin:
        return redirect('chipin:home')
    jr = get_object_or_404(GroupJoinRequest, id=request_id, group=group, status='pending')
    decision = request.POST.get('decision')
    if decision in ['approve', 'reject']:
        jr.status = 'approved' if decision == 'approve' else 'rejected'
        jr.reviewed_at = timezone.now()
        jr.save()
        if decision == 'approve':
            group.members.add(jr.user)
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def delete_comment(request, group_id, comment_id):
    group = get_object_or_404(Group, id=group_id)
    comment = get_object_or_404(Comment, id=comment_id, group=group)
    if request.user == comment.author or request.user == group.admin:
        comment.delete()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def create_event(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin:
        messages.error(request, 'Only the group administrator can create events.')
        return redirect('chipin:group_detail', group_id=group.id)
    if request.method == 'POST':
        name = request.POST.get('name')
        date = request.POST.get('date')
        total_spend = request.POST.get('total_spend')
        if name and date and total_spend:
            Event.objects.create(name=name, date=date, total_spend=total_spend, group=group)
            messages.success(request, 'Event created.')
            return redirect('chipin:group_detail', group_id=group.id)
    return render(request, 'chipin/create_event.html', {'group': group})

@login_required
@require_POST
def join_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    if request.user not in group.members.all():
        messages.error(request, 'You must join the group first.')
    elif request.user.profile.max_spend < event.calculate_share():
        messages.error(request, 'Your max spend is too low to join this event.')
    elif request.user in event.members.all():
        messages.info(request, 'You have already joined this event.')
    else:
        event.members.add(request.user)
        event.check_status()
        event.save()
        messages.success(request, 'You joined the event.')
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def update_event_status(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    if request.user == group.admin:
        event.check_status()
        event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def leave_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    if request.user in event.members.all():
        event.members.remove(request.user)
        event.check_status()
        event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
@require_POST
def delete_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    if request.user == group.admin:
        event.delete()
    return redirect('chipin:group_detail', group_id=group.id)
