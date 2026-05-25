from django.db import models


class Campus(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Campuses'

    def __str__(self):
        return self.name


class Department(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name='departments')
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['campus__name', 'name']
        unique_together = ('campus', 'name')

    def __str__(self):
        return f'{self.name} ({self.campus.name})'


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
