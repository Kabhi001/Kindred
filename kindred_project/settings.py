"""
Django settings for kindred_project project.
Configured for production-ready Sprint 1 security & environment variables.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

from django.core.exceptions import ImproperlyConfigured

IS_PRODUCTION = os.environ.get('DJANGO_ENV', '').lower() == 'production'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required in production.")
    SECRET_KEY = 'django-insecure-kindred-hostel-roommate-matcher-key-2026'
elif IS_PRODUCTION and SECRET_KEY == 'django-insecure-kindred-hostel-roommate-matcher-key-2026':
    raise ImproperlyConfigured("Insecure default SECRET_KEY cannot be used in production.")

if IS_PRODUCTION:
    DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')
else:
    DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

allowed_hosts_raw = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw.split(',') if h.strip()]
if DEBUG:
    for dev_host in ('testserver', '127.0.0.1', 'localhost', '[::1]'):
        if dev_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(dev_host)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'matcher',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'kindred_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'kindred_project.wsgi.application'

# Database Configuration
# In production, use PostgreSQL for multi-user concurrency and row-level locking.
# Supports DATABASE_URL or individual environment variables (POSTGRES_DB, etc.).
# Falls back to SQLite for local development and test suite isolation.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    import urllib.parse as urlparse
    url = urlparse.urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': url.path[1:],
            'USER': url.username or '',
            'PASSWORD': url.password or '',
            'HOST': url.hostname or 'localhost',
            'PORT': str(url.port or 5432),
            'CONN_MAX_AGE': int(os.environ.get('CONN_MAX_AGE', 600)),
        }
    }
elif os.environ.get('DJANGO_DB_ENGINE') == 'postgresql' or (IS_PRODUCTION and os.environ.get('POSTGRES_DB')):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'kindred'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': str(os.environ.get('POSTGRES_PORT', 5432)),
            'CONN_MAX_AGE': int(os.environ.get('CONN_MAX_AGE', 600)),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 20,
            }
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Transactional Email Gateway for OTPs & Allotment Notifications
EMAIL_BACKEND = os.environ.get('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Kindred Hostel Allotments <allotments@college.edu>')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

# CSRF & Session Security
CSRF_COOKIE_HTTPONLY = False  # Must be False so frontend JS can read cookie to set X-CSRFToken header
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400 * 7 # 7-day session
X_FRAME_OPTIONS = 'DENY'

# HTTPS Security Flags (Active in production with HTTPS)
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1')
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1')