from django.contrib import admin

from accounts.models import UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_todo_list_private', 'created_at', 'updated_at')
