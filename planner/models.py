import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


def _generate_token():
    return secrets.token_urlsafe(32)


class Girl(models.Model):
    name = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=128)
    token = models.CharField(max_length=64, unique=True, default=_generate_token)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    monthly_goal = models.CharField(max_length=300, blank=True)
    points_target = models.PositiveIntegerField(default=600)
    motto = models.CharField(max_length=300, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    general_chat_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class AdminSettings(models.Model):
    """Fila única (pk=1) con la contraseña de la administradora, para que pueda
    cambiarla ella misma. Si no existe fila, se usa settings.PLANNER_ADMIN_PASSWORD."""
    password_hash = models.CharField(max_length=128, blank=True)
    general_chat_read_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)


class TaskCatalogItem(models.Model):
    CATEGORY_CHOICES = [
        ('ventas', 'Ventas y prospección'),
        ('contenido', 'Contenido y marketing'),
        ('estrategia', 'Estrategia y negocio'),
        ('finanzas', 'Finanzas'),
        ('perfil', 'Marca personal'),
        ('personal', 'Día personal'),
        ('habito', 'Hábito diario'),
        ('cierre', 'Cierre de mes'),
    ]

    title = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    default_points = models.PositiveSmallIntegerField(default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['category', 'order', 'title']

    def __str__(self):
        return self.title


class CalendarEntry(models.Model):
    girl = models.ForeignKey(Girl, on_delete=models.CASCADE, related_name='entries')
    date = models.DateField()
    catalog_item = models.ForeignKey(
        TaskCatalogItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='entries'
    )
    custom_title = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=20, choices=TaskCatalogItem.CATEGORY_CHOICES, blank=True)
    points = models.PositiveSmallIntegerField(default=0)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'id']

    @property
    def title(self):
        if self.custom_title:
            return self.custom_title
        return self.catalog_item.title if self.catalog_item else ''


class GirlMessage(models.Model):
    SENDER_CHOICES = [('admin', 'Katerina'), ('girl', 'Alumna')]

    girl = models.ForeignKey(Girl, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES, default='admin')
    text = models.TextField()
    reaction = models.CharField(max_length=8, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class GeneralMessage(models.Model):
    """Canal grupal: visible para Katerina y todas las alumnas."""
    SENDER_CHOICES = [('admin', 'Katerina'), ('girl', 'Alumna')]

    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    sender_girl = models.ForeignKey(Girl, on_delete=models.SET_NULL, null=True, blank=True, related_name='general_messages')
    text = models.TextField()
    reaction = models.CharField(max_length=8, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    @property
    def sender_name(self):
        if self.sender_type == 'admin':
            return 'Katerina'
        return self.sender_girl.name if self.sender_girl else 'Alumna'


class TaskReport(models.Model):
    entry = models.OneToOneField(CalendarEntry, on_delete=models.CASCADE, related_name='report')
    category = models.CharField(max_length=20, blank=True)
    data = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
