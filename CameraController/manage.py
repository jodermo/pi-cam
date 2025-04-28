#!/usr/bin/env python
# CameraController/manage.py

import os
import sys
import pathlib

# Attempt to load .env from project root
ENV_PATH = pathlib.Path(__file__).resolve().parent / '.env'
if ENV_PATH.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=ENV_PATH)
        print(f"Loaded environment variables from {ENV_PATH}")
    except ImportError:
        print("python-dotenv not installed, skipping .env load")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_controller.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        msg = (
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        )
        print(msg, file=sys.stderr)
        raise ImportError(msg) from exc
    
    # Pass through management commands
    execute_from_command_line(sys.argv)
    
if __name__ == '__main__':
    main()