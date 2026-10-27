from django.contrib import admin 
from django.urls import include, path
from django.views.generic import RedirectView 

urlpatterns = [ 
	path('admin/', admin.site.urls), 
	path('users/', include(("users.urls", "users"), namespace="users")),
	path('chipin/', include(("chipin.urls", "chipin"), namespace="chipin")),
    path("accounts/login/", RedirectView.as_view(pattern_name="users:login", permanent=False)),
]