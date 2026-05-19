"""Validated input for Todo write operations."""

from django import forms


class TodoCreateForm(forms.Form):
    title = forms.CharField(max_length=255)
    notes = forms.CharField(required=False, strip=True)
