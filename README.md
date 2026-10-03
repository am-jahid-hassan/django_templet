# Django REST API

A production-ready Django REST API backend with authentication, OTP verification, async email delivery, in-app notifications, structured logging, and health monitoring.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Framework | Django 5.2 + Django REST Framework 3.16 |
| Auth | SimpleJWT (access + refresh tokens, blacklisting) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery 5 + Celery Beat |
| Image Processing | Pillow |
| Containerisation | Docker + Docker Compose |

---

## Features

- **JWT Authentication** — Register, login, logout, token refresh/verify, password change, OTP-gated password reset
- **OTP System** — Redis-backed, SHA-256 hashed, single-use, configurable TTL and length. Email channel implemented; SMS channel ready for integration
- **Async Email** — Celery task with auto-retry on SMTP failure (3 retries, exponential backoff)
- **In-app Notifications** — Create, list (paginated), mark read, mark all read, unread count
- **Unified Response Envelope** — Every response (success, error, validation failure, 404, 500) returns `{success, message, data, errors}`
- **BaseModel** — Abstract model with `created_at`, `updated_at`, `deleted_at` and built-in soft delete
- **Image Processing** — Configurable resize utility (aspect-ratio-preserving, never upscales)
- **Health Check** — Live dashboard at `GET /` covering DB, Redis, SMTP, Celery Worker, Celery Beat
- **Structured Logging** — Non-blocking `QueueHandler` with request-scoped context via `contextvars`
- **Rate Limiting** — Per-scope throttling on register, login, password change, OTP

---

## Project Structure

```
├── authentication/       # User model, JWT auth, password flows
├── otp/                  # OTP generation, verification, delivery rules
├── emails/               # Email tasks, logs, OTP email service
├── notifications/        # In-app notification model, service, API
├── logs/                 # Structured system log model and middleware
├── core/                 # Shared foundation
│   ├── health/           # Per-service health check functions
│   ├── services/         # health_report() aggregator
│   ├── utils/            # response, exception_handler, pagination,
│   │                     # image, validators, generators, decorators, query
│   └── models.py         # BaseModel (abstract)
├── my_django/            # Django project config, settings, URLs, Celery
│   ├── settings.py
│   ├── urls.py
│   ├── urls_v1.py
│   └── celery.py
├── tests/                # Automated pytest suite (unit, integration, api, workflows)
├── developer_guide/      # Response, Services, Utilities reference docs
├── docker/               # Dockerfile, entrypoint.sh
├── docker-compose.local.yml
├── docker-compose.prod.yml
└── requirements.txt
```

---

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
```

Edit `.env` with your values — see [Environment Variables](#environment-variables) below.

### 2. Run with Docker (recommended)

```bash
docker compose -f docker-compose.local.yml up -d --build
```

The web container automatically runs `makemigrations` and `migrate` on startup.

| Service | URL |
|---|---|
| API | http://localhost:8080 |
| Health dashboard | http://localhost:8080/ |
| pgAdmin | http://localhost:5050 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### 3. Run locally (without Docker)

```bash
# Activate virtual environment
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver

# In separate terminals:
celery -A my_django.celery worker -l info
celery -A my_django.celery beat -l info
```

---

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key | `django-insecure-...` |
| `DEBUG` | Debug mode | `True` / `False` |
| `ALLOWED_HOSTS` | Allowed hosts | `*` or `api.example.com` |
| `DB_NAME` | PostgreSQL database name | `mydb` |
| `DB_USER` | PostgreSQL user | `myuser` |
| `DB_PASSWORD` | PostgreSQL password | `securepassword` |
| `DB_HOST` | PostgreSQL host | `db` (Docker) or `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://localhost:6379/0` |
| `EMAIL_HOST` | SMTP host | `smtp.gmail.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | SMTP username | `you@gmail.com` |
| `EMAIL_HOST_PASSWORD` | SMTP password / app password | `xxxx xxxx xxxx xxxx` |
| `EMAIL_USE_TLS` | Use TLS | `True` |
| `OTP_LENGTH` | OTP digit length | `6` |
| `OTP_EXPIRY_MINUTES` | OTP lifetime | `5` |
| `OTP_CHANNEL` | Default OTP channel | `email` |
| `MAX_ACTIVE_OTPS` | Max active OTPs per user per purpose | `5` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | JWT access token lifetime | `60` |
| `REFRESH_TOKEN_LIFETIME_DAYS` | JWT refresh token lifetime | `30` |
| `LOGIN_THROTTLE_RATE_PER_MINUTE` | Login rate limit | `10` |
| `REGISTER_THROTTLE_RATE_PER_MINUTE` | Register rate limit | `5` |
| `CHANGE_PASSWORD_THROTTLE_RATE_PER_MINUTE` | Password change rate limit | `3` |
| `GET_OTP_THROTTLE_RATE_PER_DAY` | OTP request rate limit | `10` |

---

## API Reference

All endpoints are prefixed with `/v1/`. All responses follow the unified envelope:

```json
{
  "success": true,
  "message": "...",
  "data": null,
  "errors": null
}
```

### OTP

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/v1/otp/get-otp/` | No | Request an OTP (registration, password reset, etc.) |

**Body:**
```json
{ "purpose": "registration", "user_identifier": "user@example.com", "otp_channel": "email" }
```

**Purposes:** `registration`, `password_reset`, `password_change`, `login`, `verification`, `change_email`, `change_phone`, `change_username`

---

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/v1/auth/register/` | No | Register with OTP verification |
| POST | `/v1/auth/login/` | No | Login, returns access + refresh tokens |
| POST | `/v1/auth/logout/` | Yes | Blacklist refresh token |
| GET | `/v1/auth/verify/` | Yes | Verify token and return current user |
| POST | `/v1/auth/token/refresh/` | No | Rotate refresh token |
| POST | `/v1/auth/token/verify/` | No | Verify token validity |
| POST | `/v1/auth/password/change/` | Yes | Change password (requires current password) |
| POST | `/v1/auth/password/reset/` | No | Reset password via OTP |

**Register body:**
```json
{ "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com", "password": "StrongPass1!", "otp": "482910" }
```

**Login body:**
```json
{ "email": "jane@example.com", "password": "StrongPass1!" }
```

**Password reset body:**
```json
{ "email": "jane@example.com", "otp": "482910", "new_password": "NewStrongPass1!" }
```

---

### Notifications

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/v1/notifications/` | Yes | List notifications (paginated) |
| GET | `/v1/notifications/unread-count/` | Yes | Unread notification count |
| PATCH | `/v1/notifications/<id>/read/` | Yes | Mark one notification as read |
| PATCH | `/v1/notifications/read-all/` | Yes | Mark all notifications as read |

**Paginated list response:**
```json
{
  "success": true,
  "message": "Notifications retrieved",
  "data": {
    "count": 10,
    "next": "http://localhost:8080/v1/notifications/?page=2",
    "previous": null,
    "results": [...]
  }
}
```

---

### Health Check

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/` | No | HTML health dashboard |

Checks: Database, Redis, Email Service (SMTP), Celery Worker, Celery Beat.

---

## Authentication Flow

### Registration

```
1. POST /v1/otp/get-otp/    { purpose: "registration", user_identifier: "email" }
2. POST /v1/auth/register/  { email, first_name, last_name, password, otp }
```

### Password Reset

```
1. POST /v1/otp/get-otp/         { purpose: "password_reset", user_identifier: "email" }
2. POST /v1/auth/password/reset/ { email, otp, new_password }
```

---

## Developer Guide

Internal reference documentation is in [`developer_guide/`](developer_guide/):

- [`Services.md`](developer_guide/Services.md) — All service functions and classes across every app
- [`Utilities.md`](developer_guide/Utilities.md) — All utility helpers (response, pagination, image, validators, etc.)
- [`Response.md`](developer_guide/Response.md) — Unified response system reference

---

## Running Tests

Run the automated test suite using `pytest`:

```bash
pytest
```

To run a specific test suite:

```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/api/
pytest tests/workflows/
```

---

## Production Deployment

Use `docker-compose.prod.yml` with a pre-built image:

```bash
IMAGE_TAG=latest docker compose -f docker-compose.prod.yml up -d
```

Production compose runs Gunicorn (2 workers, 2 threads) instead of the development server. Ensure `DEBUG=False` and a strong `SECRET_KEY` in your production `.env`.
