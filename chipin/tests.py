from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Group, GroupJoinRequest, JoinRequestVote, Invite


class JoinRequestTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='owner@example.com', password='pass12345')
        self.member = User.objects.create_user(username='member@example.com', password='pass12345')
        self.applicant = User.objects.create_user(username='new@example.com', password='pass12345')
        self.stranger = User.objects.create_user(username='stranger@example.com', password='pass12345')
        self.group = Group.objects.create(name='Test group', admin=self.admin)
        self.group.members.add(self.admin, self.member)
        self.join_url = reverse('chipin:request_to_join', args=[self.group.pk])

    def test_join_request_created_and_not_duplicated(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.post(self.join_url).status_code, 302)
        self.client.post(self.join_url)
        self.assertEqual(GroupJoinRequest.objects.filter(group=self.group, user=self.applicant).count(), 1)

    def test_join_request_requires_post(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.join_url).status_code, 405)

    def test_member_votes_require_majority(self):
        jr = GroupJoinRequest.objects.create(group=self.group, user=self.applicant)
        url = reverse('chipin:vote_join_request', args=[self.group.pk, jr.pk])
        self.client.force_login(self.member)
        self.client.post(url, {'vote': 'yes'})
        jr.refresh_from_db()
        self.assertEqual(jr.status, GroupJoinRequest.PENDING)
        self.client.force_login(self.admin)
        self.client.post(url, {'vote': 'yes'})
        jr.refresh_from_db()
        self.assertEqual(jr.status, GroupJoinRequest.APPROVED)
        self.assertTrue(self.group.members.filter(pk=self.applicant.pk).exists())

    def test_nonmember_cannot_vote(self):
        jr = GroupJoinRequest.objects.create(group=self.group, user=self.applicant)
        self.client.force_login(self.stranger)
        self.client.post(reverse('chipin:vote_join_request', args=[self.group.pk, jr.pk]), {'vote': 'yes'})
        self.assertFalse(JoinRequestVote.objects.filter(join_request=jr).exists())

    def test_only_admin_can_directly_approve(self):
        jr = GroupJoinRequest.objects.create(group=self.group, user=self.applicant)
        url = reverse('chipin:review_join_request', args=[self.group.pk, jr.pk])
        self.client.force_login(self.member)
        self.client.post(url, {'decision': 'approve'})
        jr.refresh_from_db()
        self.assertEqual(jr.status, GroupJoinRequest.PENDING)
        self.client.force_login(self.admin)
        self.client.post(url, {'decision': 'approve'})
        jr.refresh_from_db()
        self.assertEqual(jr.status, GroupJoinRequest.APPROVED)

    def test_invite_cannot_be_claimed_by_other_user(self):
        invite = Invite.objects.create(group=self.group, invited_user=self.applicant, invited_by=self.admin)
        self.client.force_login(self.stranger)
        url = reverse('chipin:accept_invite', args=[invite.token])
        self.client.post(url)
        self.assertFalse(self.group.members.filter(pk=self.stranger.pk).exists())
        self.assertFalse(self.group.members.filter(pk=self.applicant.pk).exists())


from .models import Comment


class GroupChatTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='chat-owner@example.com', password='pass12345')
        self.member = User.objects.create_user(username='chat-member@example.com', password='pass12345')
        self.outsider = User.objects.create_user(username='chat-outsider@example.com', password='pass12345')
        self.group = Group.objects.create(name='Study Group', admin=self.owner)
        self.group.members.add(self.owner, self.member)
        self.chat_url = reverse('chipin:group_chat', args=[self.group.pk])
        self.post_url = reverse('chipin:post_comment', args=[self.group.pk])

    def test_member_can_post_and_read(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.post_url, {'content': 'Hello group!'}).status_code, 302)
        self.assertContains(self.client.get(self.chat_url), 'Hello group!')

    def test_nonmember_cannot_read_or_post(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.chat_url).status_code, 302)
        self.client.post(self.post_url, {'content': 'Intruder'})
        self.assertFalse(Comment.objects.filter(group=self.group).exists())

    def test_html_is_sanitised_and_output_escaped(self):
        self.client.force_login(self.member)
        self.client.post(self.post_url, {'content': '<script>alert(1)</script><b>Hello</b> & hi'})
        comment = Comment.objects.get(group=self.group)
        self.assertNotIn('<script>', comment.content)
        response = self.client.get(self.chat_url)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'Hello')

    def test_only_author_can_edit(self):
        comment = Comment.objects.create(group=self.group, author=self.member, content='Original')
        url = reverse('chipin:edit_comment', args=[self.group.pk, comment.pk])
        self.client.force_login(self.owner)
        self.client.post(url, {'content': 'Admin edit'})
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Original')
        self.client.force_login(self.member)
        self.client.post(url, {'content': 'Updated'})
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Updated')

    def test_member_cannot_delete_other_member_comment_but_admin_can(self):
        other_member = User.objects.create_user(username='chat-extra@example.com', password='pass12345')
        self.group.members.add(other_member)
        comment = Comment.objects.create(group=self.group, author=other_member, content='Message')
        url = reverse('chipin:delete_comment', args=[self.group.pk, comment.pk])
        self.client.force_login(self.member)
        self.client.post(url)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())
        self.client.force_login(self.owner)
        self.client.post(url)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    def test_delete_requires_post(self):
        comment = Comment.objects.create(group=self.group, author=self.member, content='Message')
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('chipin:delete_comment', args=[self.group.pk, comment.pk])).status_code, 405)
