from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """Every user always has an associated Profile row."""
    if created:
        Profile.objects.get_or_create(user=instance)
