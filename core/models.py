import uuid
import random
from django.db import models


def _gen_short_id():
    return str(random.randint(100000, 999999))


class ChatSession(models.Model):
    session_id    = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    short_id      = models.CharField(max_length=8, unique=True, default=_gen_short_id)
    trigger       = models.CharField(max_length=32, default='timer')
    page_time_sec = models.IntegerField(default=0)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.session_id[:8]} ({'active' if self.is_active else 'closed'})"


class ChatMessage(models.Model):
    VISITOR  = 'visitor'
    OPERATOR = 'operator'
    SYSTEM   = 'system'
    SENDER_CHOICES = [
        (VISITOR,  'Visitor'),
        (OPERATOR, 'Operator'),
        (SYSTEM,   'System'),
    ]

    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender     = models.CharField(max_length=16, choices=SENDER_CHOICES)
    text       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender}] {self.text[:60]}"
