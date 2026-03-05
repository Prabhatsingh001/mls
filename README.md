# mls

## Database Schema & Relationships

### User (authentication.User)
- email (unique)
- full_name
- phone_number
- address
- role: ADMIN | TECH | CUST
- signup_method: email | phone
- phone_verified
- is_active, is_staff, date_joined

### PhoneOTP (authentication.PhoneOTP)
- user (FK → User)
- otp
- created_at, expires_at, is_used

### Category (services.Category)
- name (unique)
- slug (unique)
- description

### Service (services.Service)
- category (FK → Category)
- title
- description
- base_price
- is_active

### JobRequest (services.JobRequest)
- customer (FK → User, role=CUST)
- service (FK → Service)
- description
- site_address
- preferred_date
- created_at
- is_reviewed, is_converted_to_project

### Project (services.Project)
- source_request (OneToOne → JobRequest)
- technician (FK → User, role=TECH, nullable)
- status: Pending | Scheduled | Ongoing | Completed | Cancelled
- quoted_amount
- start_date, completion_date
- notes

---

#### Relationships Diagram (textual)

User ──< PhoneOTP
User ──< JobRequest >── Service >── Category
JobRequest ──1:1── Project
Project ──> Technician (User, role=TECH)

All foreign keys use CASCADE unless otherwise noted.