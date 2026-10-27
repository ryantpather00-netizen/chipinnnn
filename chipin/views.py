from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from .models import Group, Invite
from .forms import GroupCreationForm
from django.urls import reverse

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
def group_detail(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    return render(request, 'chipin/group_detail.html', {'group': group})

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

    # Only the group admin can create invites
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can invite members.")
        return redirect("chipin:group_detail", group_id=group.id)

    # Users who are not in the group (and aren’t the admin if you wish)
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
        if invite.is_expired():
            invite.expires_at = timezone.now() + timezone.timedelta(days=14)
            invite.accepted = False
            invite.save(update_fields=["expires_at", "accepted"])

        return redirect("chipin:web3forms_invite", group_id=group.id, invite_id=invite.id)

    return render(
        request,
        "chipin/invite_users.html",
        {"group": group, "users_not_in_group": users_not_in_group},
    )

@login_required
def web3forms_invite(request, group_id, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, group_id=group_id)
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

def accept_invite(request, token):
    invite = get_object_or_404(Invite, token=token)
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