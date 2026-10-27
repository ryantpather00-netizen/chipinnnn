import secrets, requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm, EmailAuthenticationForm

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

def _hp_name(request):
    # stable per-session honeypot name to defeat autofill/scripts
    if "hp_name" not in request.session:
        request.session["hp_name"] = f"hp_{secrets.token_hex(8)}"
    return request.session["hp_name"]

def login_view(request):
    hp_name = _hp_name(request)

    if request.method == "POST":
        # 1) Honeypot (cheap check first)
        if request.POST.get(hp_name):
            messages.error(request, "Bot detected.")
            return redirect("users:login")

        # 2) Timing guard (humans rarely submit under 1.5s)
        try:
            elapsed = float(request.POST.get("elapsed", 0))
            if elapsed < 1.5:
                messages.error(request, "Please wait a moment before submitting.")
                return redirect("users:login")
        except (TypeError, ValueError):
            pass

        # 3) reCAPTCHA verify (network call after cheap checks)
        token = request.POST.get("recaptcha-token")
        data = {
            "secret": settings.RECAPTCHA_SECRET_KEY,
            "response": token,
            "remoteip": request.META.get("REMOTE_ADDR"),
        }
        try:
            resp = requests.post(RECAPTCHA_VERIFY_URL, data=data, timeout=3.0)
            result = resp.json()
        except requests.RequestException:
            result = {"success": False}

        if not result.get("success"):
            messages.error(request, "reCAPTCHA validation failed. Please try again.")
            return redirect("users:login")

        # 4) Authenticate
        username = (request.POST.get("username") or "").strip().lower()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # rotate honeypot name after each successful POST
            request.session["hp_name"] = f"hp_{secrets.token_hex(8)}"
            next_url = request.GET.get("next", reverse("chipin:home"))
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
            return redirect("users:login")

    # GET: render with the current hp_name
    next_url = request.GET.get("next", "")
    return render(request, "users/login.html", {"hp_name": hp_name, "next": next_url})

def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account has been created! You can now log in.")
            return redirect('users:login')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

@login_required(login_url='users:login')
def user(request):
    return render(request, "chipin/home.html")

def logout_view(request):
    logout(request)
    messages.success(request, "Successfully logged out.")
    return redirect('users:login')