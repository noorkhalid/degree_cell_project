from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from accounts.models import UserProfile


def user_role(user):
    if user.is_superuser:
        return UserProfile.Role.ADMIN
    return getattr(getattr(user, 'profile', None), 'role', None)


def is_admin(user):
    return user.is_superuser or user_role(user) == UserProfile.Role.ADMIN


def is_desk(user):
    return is_admin(user) or user_role(user) == UserProfile.Role.DESK


def is_printing(user):
    return is_admin(user) or user_role(user) == UserProfile.Role.PRINTING


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = user_role(request.user)
            if is_admin(request.user) or role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to perform this action.')
            return redirect('dashboard')
        return wrapper
    return decorator
