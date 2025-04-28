import os
import dj_database_url
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Secret key & debug
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'your-default-secret-key')
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')

# Hosts
ALLOWED_HOSTS = os.getenv(
    'DJANGO_ALLOWED_HOSTS',
    f"127.0.0.1,localhost,{os.getenv('DOMAIN','really.dont-use.com')}"
).split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',  # for serving static files
    'controller',                  # your camera controller app
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'camera_controller.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / 'controller' / 'templates' ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.static',
            ],
        },
    },
]

WSGI_APPLICATION = 'camera_controller.wsgi.application'

# Database (Postgres via dj-database-url)
DATABASES = {
    'default': dj_database_url.parse(
        os.getenv('DATABASE_URL'),
        conn_max_age=600
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (collected to STATIC_ROOT, served by nginx)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Media files (user uploads, served by nginx)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom camera controller settings
CAMERA_API_URL = os.getenv('CAMERA_API_URL', '/api')
CAMERA_LOCATIONS = [
    loc.strip() for loc in os.getenv('CAMERA_LOCATIONS', '').split(',')
    if loc.strip()
]


# URL where requests are redirected for login (must match your login_view path)
LOGIN_URL = '/login/'

# After login, redirect here by default
LOGIN_REDIRECT_URL = '/'

# (Optional) After logout, redirect here
LOGOUT_REDIRECT_URL = '/login/'