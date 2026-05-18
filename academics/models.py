from django.db import models


class Institute(models.Model):
    class Category(models.TextChoices):
        UNIVERSITY = 'UNIVERSITY', 'University Teaching Department'
        GOVT = 'GOVT', 'Government Affiliated College'
        PRIVATE = 'PRIVATE', 'Private Affiliated College'

    name = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Program(models.Model):
    class Level(models.TextChoices):
        BACHELOR = 'BACHELOR', 'Bachelor'
        MASTER = 'MASTER', 'Master'
        MPHIL = 'MPHIL', 'MPhil'
        PHD = 'PHD', 'PhD'
        DIPLOMA = 'DIPLOMA', 'Diploma'
        OTHER = 'OTHER', 'Other'

    name = models.CharField(max_length=255, unique=True)
    level = models.CharField(max_length=20, choices=Level.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['level', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_level_display()})'


class Bank(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CourierCompany(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Courier companies'

    def __str__(self):
        return self.name
