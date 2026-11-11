from django import forms
from .models import Group, Comment

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter your comment...'})
        }
    def clean_content(self):
        content = self.cleaned_data.get('content')
        if "<script>" in content.lower():
            raise forms.ValidationError("Invalid content.")
        return content

class GroupCreationForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        group = super().save(commit=False)
        group.admin = self.user
        if commit:
            group.save()
            group.members.add(self.user)
        return group