# MLS — Micro Labor Services

A full-featured Django platform that connects **customers** with **technicians** for on-demand home and maintenance services. Admins manage the entire lifecycle — from service catalogs and job requests to project assignments and completion tracking.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.2, Python |
| Database | PostgreSQL 16 |
| Task Queue | Celery 5.6 + Redis 7 |
| Auth | Email/Password, Phone OTP, Google OAuth 2.0 |
| Frontend | Django Templates, Tailwind CSS |
| Infrastructure | Docker Compose (Redis & Postgres) |

---

## Project Structure

```
mls/                  # Django project settings, urls, celery config
authentication/       # Custom User model, registration, login, OTP, OAuth, profiles
services/             # Categories, Services, JobRequests, Projects, Technician dashboard
customerapp/          # Customer dashboard — browse services, submit & track requests
adminapp/             # Admin panel — manage users, technicians, services, jobs, projects
billing/              # Billing module (placeholder)
theme/                # Tailwind CSS theme app
templates/            # Global templates (navbar, footer, index)
static/               # Static assets
media/                # User uploads (profile pictures, Aadhar images)
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js (for Tailwind CSS)
- Docker & Docker Compose

### 1. Clone & Install

```bash
git clone https://github.com/Prabhatsingh001/mls.git
cd mls
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
SUPPORT_EMAIL=support@example.com
```

### 3. Start Services (Redis & PostgreSQL)

```bash
docker-compose up -d
```

### 4. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Tailwind CSS

```bash
python manage.py tailwind install
python manage.py tailwind start    # dev watch mode
```

### 6. Start Celery Worker

```bash
celery -A mls worker --loglevel=info --pool=solo
```

### 7. Run Development Server

```bash
python manage.py runserver
```

---

## Authentication

The platform supports three authentication methods:

| Method | Flow |
|--------|------|
| **Email** | Register → Email verification link → Activate → Login |
| **Phone** | Register with phone → OTP sent → Verify OTP → Login |
| **Google OAuth** | Login with Google → Auto-create account → Role selection |

Password reset is handled via email with secure token-based links. All emails are sent asynchronously through Celery.

---

## User Roles & Access Control

| Role | Access |
|------|--------|
| **ADMIN** | Full platform management — users, technicians, services, categories, job requests, projects |
| **TECHNICIAN** | View assigned projects, update project status (Ongoing → Completed) |
| **CUSTOMER** | Browse services, submit job requests, track project progress, cancel pending requests |

Access is enforced via a `@role_required` decorator and `RoleRequiredMiddleware`.

---

## Job Request → Project Lifecycle

```
Customer submits Job Request
        │
        ▼
Admin reviews request (marks reviewed)
        │
        ▼
Admin converts to Project (sets quoted amount, optional technician & start date)
        │
        ▼
Technician marks project Ongoing (start date recorded)
        │
        ▼
Technician marks project Completed (completion date recorded)
```

**Project Statuses:** `Pending` → `Scheduled` → `Ongoing` → `Completed` | `Cancelled`

---

## API Endpoints

### Authentication (`/a/`)

| Endpoint | Description |
|----------|-------------|
| `register/` | Email or phone registration |
| `login/` | Email or phone login |
| `logout/` | Logout |
| `activate/<uidb64>/<token>/` | Email verification |
| `verify-phone-otp/<user_id>/` | OTP verification |
| `forgot_password/` | Initiate password reset |
| `reset_password/<uidb64>/<token>/` | Complete password reset |
| `profile/<user_id>/` | View profile |
| `edit-profile/<user_id>/` | Edit profile |
| `choose-role/` | Select role after signup |

### Customer (`/customer/`)

| Endpoint | Description |
|----------|-------------|
| ` ` (root) | Dashboard — services, requests, projects |
| `create-request/` | Submit a new job request |
| `cancel-request/<id>/` | Cancel a pending request |

### Technician (`/services/`)

| Endpoint | Description |
|----------|-------------|
| `dashboard/` | View assigned projects & stats |
| `project/<id>/` | Project details |
| `project/<id>/update-status/` | Update project status |

### Admin Panel (`/panel/`)

| Endpoint | Description |
|----------|-------------|
| `dashboard/` | Multi-tab admin dashboard |
| `toggle-active/<user_id>/` | Activate / deactivate user |
| `make-admin/<user_id>/` | Promote user to admin |
| `remove-admin/<user_id>/` | Demote admin to customer |
| `create-category/` | Create service category |
| `edit-category/<id>/` | Edit category |
| `delete-category/<id>/` | Delete category |
| `create-service/` | Create service |
| `edit-service/<id>/` | Edit service |
| `delete-service/<id>/` | Delete service |
| `toggle-service/<id>/` | Toggle service active status |
| `user/<user_id>/` | View user details |
| `update-tech-status/<user_id>/` | Update technician verification |
| `request/<id>/` | View job request details |
| `request/<id>/mark-reviewed/` | Mark request as reviewed |
| `request/<id>/convert-to-project/` | Convert request to project |
| `request/<id>/assign-technician/` | Assign technician |
| `project/<id>/update-status/` | Update project status |
| `project/<id>/update-start-date/` | Update project start date |

---

## Database Schema

### Models

**User** — Custom user model (email as username)
- `email`, `full_name`, `phone_number`, `role`, `signup_method`, `phone_verified`, `is_active`, `is_staff`, `date_joined`

**TechnicianProfile** (1:1 → User)
- `skills` (JSON), `experience_years`, `address`, `profile_picture`, `aadhar_image`, `verification_status`

**CustomerProfile** (1:1 → User)
- `created_at`

**Address** (FK → CustomerProfile)
- `street`, `city`, `state`, `postal_code`, `country`, `is_primary`

**PhoneOTP** (FK → User)
- `otp`, `created_at`, `expires_at`, `is_used`

**Category**
- `name`, `slug`, `description`

**Service** (FK → Category)
- `title`, `description`, `base_price`, `is_active`

**JobRequest** (FK → User, FK → Service)
- `description`, `site_address`, `preferred_date`, `is_reviewed`, `is_converted_to_project`, `is_project_completed`

**Project** (1:1 → JobRequest, FK → User as technician)
- `status`, `quoted_amount`, `start_date`, `completion_date`, `notes`

### Relationships

```
User ──1:1── TechnicianProfile
User ──1:1── CustomerProfile ──< Address
User ──< PhoneOTP
User ──< JobRequest >── Service >── Category
JobRequest ──1:1── Project ──> User (Technician)
```

---

## Celery Tasks

| Task | Trigger |
|------|---------|
| `send_verification_mail` | Email registration |
| `send_reset_password_email` | Forgot password |
| `password_reset_success_email` | After password reset |
| `send_welcome_email` | Post-activation (planned) |

All tasks send HTML + plain text emails and run asynchronously via Redis broker with Django DB result backend.