"""WSGI entry point. Gunicorn binds the application to an internal Docker network."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "compassapp.settings")
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
