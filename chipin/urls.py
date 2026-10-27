from django.urls import path
from . import views

urlpatterns = [
   path("", views.home, name="home"), 
   path('create_group/', views.create_group, name='create_group'),
   path('group/<int:group_id>/delete/', views.delete_group, name='delete_group'),
   path('group/<int:group_id>/', views.group_detail, name='group_detail'),
   path('group/<int:group_id>/invite/', views.invite_users, name='invite_users'),
   path("group/<int:group_id>/leave/", views.leave_group, name="leave_group"),
   path("invites/accept/<uuid:token>/", views.accept_invite, name="accept_invite"),
   path("groups/<int:group_id>/invite/<int:invite_id>/send/", views.web3forms_invite, name="web3forms_invite"),
   path("invites/sent/", views.invite_sent, name="invite_sent"),
]