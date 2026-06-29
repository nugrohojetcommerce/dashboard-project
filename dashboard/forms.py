# dashboard/forms.py
from django import forms
from django.contrib.auth.models import User

class UserProfileForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')