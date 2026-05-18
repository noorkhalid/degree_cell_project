from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        DESK = 'DESK', 'Desk Officer'
        PRINTING = 'PRINTING', 'Printing Officer'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DESK)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} - {self.get_role_display()}'
