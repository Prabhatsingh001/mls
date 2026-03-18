# MLS - Micro Labor Services

MLS is a Django-based service marketplace where customers raise home-service requests, admins review and convert requests into projects, and technicians execute and update project progress.

## What This Project Includes

- Custom authentication with email/password, phone OTP, and Google OAuth
- Role-driven dashboards for Admin, Technician, and Customer
- Service catalog management with categories, services, and item mappings
- Job request to project conversion workflow
- Technician-side project updates and extra material tracking
- In-app notifications plus Web Push subscription support
- Celery-based async tasks for email, notifications, and scheduled reminders

## Tech Stack

| Layer | Tech |
| --- | --- |
| Backend | Django 5.2 |
| Language | Python |
| Database | PostgreSQL 16 |
| Queue/Broker | Celery 5.6 + Redis 7 |
| Scheduler | django-celery-beat |
| Task Results | django-celery-results |
| Auth | Session auth, Phone OTP, Google OAuth (social-auth-app-django) |
| Frontend | Django Templates + Tailwind CSS |
| Notifications | DB notifications, Web Push, optional SMS via Twilio |

## Project Apps

| App | Responsibility |
| --- | --- |
| `authentication` | Custom user model, registration/login, OTP, profile, password reset, role flow |
| `services` | Category/service catalog, job requests, projects, service items, extra materials |
| `customerapp` | Customer dashboard and job request operations |
| `adminapp` | Admin operations for users, technicians, catalog, requests, and projects |
| `notification` | Notification models, inbox views, push subscription APIs, reminder tasks |
| `billing` | Billing app scaffold (minimal at the moment) |
| `theme` | Tailwind app integration |

## Quick Start (Local)

### 1. Clone and install dependencies

```bash
git clone https://github.com/Prabhatsingh001/mls.git
cd mls

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Create `.env` file

Create `.env` in the repository root.

Required keys:

```env
SECRET_KEY=your-django-secret

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
SUPPORT_EMAIL=support@example.com

VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_ADMIN_EMAIL=admin@example.com

# Optional (needed only if you enable SMS sending)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
```

### 3. Start Redis and Postgres

```bash
docker compose up -d
```

### 4. Apply migrations and create admin

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Start Tailwind watcher (optional for active UI development)

```bash
python manage.py tailwind install
python manage.py tailwind start
```

### 6. Run Django and workers

Run these in separate terminals:

```bash
python manage.py runserver
```

```bash
celery -A mls worker --loglevel=info --pool=solo
```

```bash
celery -A mls beat --loglevel=info
```

## URL Map

Base route groups from the project router:

- `/` - landing/index
- `/a/` - authentication and profile flows
- `/panel/` - admin operations
- `/customer/` - customer dashboard/actions
- `/services/` - technician dashboard/actions
- `/notifications/` - notification inbox + push subscription APIs
- `/auth/` - social-auth endpoints

## Key Endpoints

### Authentication (`/a/`)

- `register/`
- `login/`
- `logout/`
- `activate/<uidb64>/<token>/`
- `verify-phone-otp/<int:user_id>/`
- `resend-phone-otp/<int:user_id>/`
- `forgot_password/`
- `reset_password/<uidb64>/<token>/`
- `profile/<int:user_id>/`
- `edit-profile/<int:user_id>/`
- `update-password/<int:user_id>/`
- `choose-role/`
- `redirect-dashboard/`

### Customer (`/customer/`)

- `dashboard/` (dashboard)
- `create-request/`
- `edit-request/<int:job_request_id>/`
- `request-detail/<int:job_request_id>/`
- `cancel-request/<int:request_id>/`

### Technician (`/services/`)

- `dashboard/`
- `toggle-availability/`
- `join/`
- `project/<int:project_id>/`
- `project/<int:project_id>/update-status/`
- `project/<int:project_id>/extra-materials/add/`

### Admin (`/panel/`)

- `dashboard/`
- `toggle-active/<int:user_id>/`
- `make-admin/<int:user_id>/`
- `remove-admin/<int:user_id>/`
- category/service/service-item management endpoints
- request review, technician assignment, and project status/update endpoints

### Notifications (`/notifications/`)

- `/` (notification list)
- `<int:notification_id>/read/`
- `mark-all-read/`
- `unread-count/`
- `push/vapid-key/`
- `push/subscribe/`

## Core Workflow

1. Customer creates a `JobRequest`.
2. Admin reviews and optionally assigns a technician.
3. Admin converts the request into a `Project` with quote and schedule.
4. Technician updates status (`PENDING` -> `SCHED` -> `ONGOING` -> `COMPLETED` or `CANCELLED`).
5. Technician can add project extra materials when needed.

## Database Schema

### Core Tables

| Table | Key Fields |
| --- | --- |
| `authentication_user` | `email` (unique), `full_name`, `phone_number`, `role`, `signup_method`, `phone_verified`, `email_verified`, `is_active`, `is_blocked` |
| `authentication_technicianprofile` | `user` (one-to-one), `skills` (JSON), `experience_years`, `verification_status`, `is_available` |
| `authentication_customerprofile` | `user` (one-to-one), `created_at` |
| `authentication_address` | `customer` (FK), `street`, `city`, `state`, `postal_code`, `country`, `is_primary` |
| `authentication_phoneotp` | `user` (FK), `otp`, `expires_at`, `is_used` |
| `services_category` | `name` (unique), `slug` (unique), `description` |
| `services_service` | `category` (FK), `title`, `description`, `base_price`, `is_active` |
| `services_serviceitem` | `name`, `item_type`, `unit_cost`, `is_available` |
| `services_serviceitemmapping` | `service` (FK), `item` (FK), `quantity`, `is_optional`, `extra_cost`, `display_order` |
| `services_jobrequest` | `customer` (FK), `service` (FK), `description`, `site_address`, `preferred_date`, `is_reviewed`, `is_converted_to_project` |
| `services_project` | `job_request` (one-to-one), `technician` (FK, nullable), `status`, `quoted_amount`, `start_date`, `completion_date` |
| `services_projectextramaterial` | `project` (FK), `catalog_item` (FK, nullable), `added_by` (FK, nullable), `material_name`, `quantity`, `unit_cost` |
| `notification_notification` | `user` (FK), `type`, `title`, `message`, `is_read`, `content_type` + `object_id` (generic reference) |
| `notification_pushsubscription` | `user` (FK), `endpoint`, `p256dh`, `auth` (unique together: `user`, `endpoint`) |

### Relationship Overview

```text
User (authentication_user)
|- 1:1 -> TechnicianProfile
|- 1:1 -> CustomerProfile
|- 1:M -> PhoneOTP
|- 1:M -> JobRequest (as customer)
|- 1:M -> Project (as technician, nullable)
|- 1:M -> ProjectExtraMaterial (added_by, nullable)
|- 1:M -> Notification
`- 1:M -> PushSubscription

CustomerProfile
`- 1:M -> Address

Category
`- 1:M -> Service

Service
|- 1:M -> JobRequest
`- 1:M -> ServiceItemMapping

ServiceItem
|- 1:M -> ServiceItemMapping
`- 1:M -> ProjectExtraMaterial (catalog_item, nullable)

JobRequest
`- 1:1 -> Project

Project
`- 1:M -> ProjectExtraMaterial

Notification
`- optional generic link -> (ContentType, object_id)
```

### Detailed Relationship Notes

Detailed explanations for each relationship (cardinality, ownership, delete behavior, and business meaning) are documented in `DATABASE_RELATIONSHIPS_DETAIL.txt`.

## Async and Scheduled Tasks

Implemented task patterns include:

- Auth emails (verification, reset password, reset success, welcome)
- Admin push/SMS notification fanout
- Daily pending-work reminder (`remind_pending_work`) via Celery Beat

## Notes for Development

- `DEBUG` is currently enabled in settings.
- Database and Redis are configured for localhost with Docker defaults.
- Role-based access is enforced in middleware and decorators.
- If push keys are missing in `.env`, notification push endpoints will fail.

## Future Expansion Areas

- Billing app implementation
- API layer (DRF) if mobile clients are planned
- CI checks and broader test coverage
- Production hardening for secrets, hosts, and debug flags
