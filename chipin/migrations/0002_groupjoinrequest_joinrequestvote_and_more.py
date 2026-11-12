

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chipin', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupJoinRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_requests', to='chipin.group')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='JoinRequestVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('approve', models.BooleanField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('join_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='chipin.groupjoinrequest')),
                ('voter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_request_votes', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='groupjoinrequest',
            constraint=models.UniqueConstraint(fields=('group', 'user'), name='unique_group_join_request'),
        ),
        migrations.AddConstraint(
            model_name='joinrequestvote',
            constraint=models.UniqueConstraint(fields=('join_request', 'voter'), name='unique_join_request_vote'),
        ),
    ]
