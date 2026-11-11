from django.urls import path
from . import views

app_name = 'chipin'

urlpatterns = [
    path('', views.home, name='home'),
    path('create_group/', views.create_group, name='create_group'),
    path('group/<int:group_id>/delete/', views.delete_group, name='delete_group'),
    path('group/<int:group_id>/', views.group_detail, name='group_detail'),
    path('group/<int:group_id>/invite/', views.invite_users, name='invite_users'),
    path('group/<int:group_id>/leave/', views.leave_group, name='leave_group'),
    path('invites/accept/<uuid:token>/', views.accept_invite, name='accept_invite'),
    path('groups/<int:group_id>/invite/<int:invite_id>/send/', views.web3forms_invite, name='web3forms_invite'),
    path('invites/', views.my_invites, name='my_invites'),
    path('invites/<int:invite_id>/decline/', views.decline_invite, name='decline_invite'),
    path('invites/sent/', views.invite_sent, name='invite_sent'),
    path('groups/', views.browse_groups, name='browse_groups'),
    path('group/<int:group_id>/join/', views.request_to_join, name='request_to_join'),
    path('group/<int:group_id>/requests/', views.group_join_requests, name='group_join_requests'),
    path('group/<int:group_id>/requests/<int:request_id>/vote/', views.vote_join_request, name='vote_join_request'),
    path('group/<int:group_id>/requests/<int:request_id>/review/', views.review_join_request, name='review_join_request'),
    path('group/<int:group_id>/chat/', views.group_chat, name='group_chat'),
    path('group/<int:group_id>/chat/post/', views.post_comment, name='post_comment'),
    path('group/<int:group_id>/chat/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('group/<int:group_id>/chat/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
]
