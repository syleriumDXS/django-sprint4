"""App configuration for pages."""
from django.apps import AppConfig


class PagesConfig(AppConfig):
    """Register the pages application."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pages'
