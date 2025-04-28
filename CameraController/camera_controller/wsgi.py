# CameraController/camera_controller/wsgi.py

import os
from django.core.wsgi import get_wsgi_application

# Set the default settings module for the 'camera_controller' project
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_controller.settings')

# Create the WSGI application object for use by Gunicorn (or another WSGI server)
application = get_wsgi_application()
