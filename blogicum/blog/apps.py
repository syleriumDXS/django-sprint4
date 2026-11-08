"""Application configuration for Blogicum."""
from django.apps import AppConfig


class BlogConfig(AppConfig):
    """Set the human-readable application title."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blog'
    verbose_name = 'Блог'
