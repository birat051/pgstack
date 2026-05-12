from django.contrib.auth.models import AnonymousUser, User
from django.db import transaction
from django.utils import timezone

from accounts.models import UserSettings


def username_for_normalized_email(normalized_email: str) -> str:
    """Deterministic username from normalized email with suffix-on-collision fallback."""
    max_length = User._meta.get_field('username').max_length
    base = normalized_email.strip().lower()[:max_length]
    if base == '':
        base = 'user'
    candidate = base
    suffix_n = 1
    while User.objects.filter(username__iexact=candidate).exists():
        suffix = f'_{suffix_n}'
        trimmed = base[: max(1, max_length - len(suffix))]
        candidate = f'{trimmed}{suffix}'
        suffix_n += 1
    return candidate


@transaction.atomic
def register_user(*, display_name: str, email: str, password: str) -> User:
    """
    Create ``User``, hash ``password``, and ensure ``UserSettings`` exists (private-by-default).

    Preconditions: callers should validate uniqueness and password strength via ``SignupForm``.
    """
    normalized = User.objects.normalize_email(email.strip())
    username = username_for_normalized_email(normalized)
    user = User.objects.create_user(
        username=username,
        email=normalized,
        password=password,
        first_name=display_name,
    )
    get_or_create_user_settings(user)
    return user


def get_or_create_user_settings(user: User) -> UserSettings:
    settings_row, _ = UserSettings.objects.get_or_create(user=user)
    return settings_row


def set_todo_list_privacy(user: User, is_private: bool) -> None:
    get_or_create_user_settings(user)
    UserSettings.objects.filter(user=user).update(
        is_todo_list_private=is_private,
        updated_at=timezone.now(),
    )


def can_view_todo_list(viewer: User | AnonymousUser, owner: User) -> bool:
    if viewer.is_authenticated and viewer.pk == owner.pk:
        return True
    owner_settings = get_or_create_user_settings(owner)
    if owner_settings.is_todo_list_private:
        return False
    return viewer.is_authenticated
