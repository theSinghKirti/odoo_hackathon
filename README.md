# Subscription Management System (Odoo Hackathon)

**Subscription Manager** is a production-grade multi-tenant SaaS application designed to manage the complete lifecycle of plans, subscriptions, and recurring billing for companies like **Brightloop Software**.

---

## Documentation Directory

All comprehensive specifications, business rules, schemas, and implementation guides are located in the [`docs/`](./docs) folder:

- [PRD.md](./docs/PRD.md) — Product Requirements Document
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) — System Architecture & Component Design
- [DATABASE_SCHEMA.md](./docs/DATABASE_SCHEMA.md) — Relational PostgreSQL Schema & Indexes
- [BUSINESS_RULES.md](./docs/BUSINESS_RULES.md) — Domain Logic & Business Rules
- [API_SPECIFICATION.md](./docs/API_SPECIFICATION.md) — Route & API Specifications
- [IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md) — Milestone Roadmap & Task Breakdown
- [AI_CONTEXT.MD](./docs/AI_CONTEXT.MD) — AI Pair Programming Context

---

## 1. Project Overview & Phase 1 Status

Phase 1 establishes the production foundation:

- **Strict Multi-Tenant Isolation**: Authoritative server-side tenant scoping based on the authenticated context (`Organization`), preventing cross-tenant data leakage or IDOR / URL tampering.
- **Robust Role-Based Access Control (RBAC)**: Support for `Admin`, `Staff`, and `Customer` roles enforced on the backend.
- **Cryptographic Security**: Argon2id password hashing, strict password validation policies, and single-use password reset tokens with SHA-256 persistence.
- **Stateless Authentication**: Signed JWTs delivered via secure, HTTP-only cookies with SameSite protection and Authorization header fallbacks.
- **Server-Rendered Interactive UI**: Jinja2 HTML templates combined with HTMX for responsive, reactive frontend interactions without heavy client-side JavaScript frameworks.
- **Reference Tenant**: Pre-configured with the reference tenant **Brightloop Software** and automated admin seeding.

---

## 2. Technology Stack

| Layer | Technology | Description |
|---|---|---|
| **Language** | Python 3.11 / 3.12 | Modern type-hinted Python runtime |
| **Backend Framework** | FastAPI | High-performance asynchronous web framework |
| **Validation & Settings** | Pydantic v2 & Pydantic-Settings | Data validation and environment configuration |
| **Database** | PostgreSQL 16+ (or SQLite Async) | ACID-compliant relational data store |
| **ORM** | SQLAlchemy 2.0 Async | Asynchronous Object-Relational Mapping (`asyncpg`, `aiosqlite`) |
| **Schema Migrations** | Alembic | Version-controlled async database migrations |
| **Password Hashing** | Argon2id (`argon2-cffi`) | Memory-hard cryptographic hashing algorithm |
| **Authentication** | JWT (`pyjwt[crypto]`) | Signed bearer tokens in HTTP-only cookies |
| **Frontend Templates** | Jinja2 | Server-side HTML template rendering |
| **Interactivity** | HTMX 1.9+ | Dynamic partial page updates without SPA complexity |
| **Styling** | Vanilla CSS | Modern, clean, responsive SaaS UI layout |
| **Background Infrastructure** | Celery & Redis | Task queue and message broker foundation |
| **Testing** | Pytest, HTTPX, Pytest-Asyncio | Asynchronous API and unit test suite |
| **Containerization** | Docker & Docker Compose | Multi-container application orchestration |

---

## 3. Prerequisites

- **Python**: 3.11 or 3.12
- **uv** (recommended) or **pip**
- **Docker & Docker Compose** (for containerized deployment)
- **PostgreSQL 16+** and **Redis** (if running locally without Docker)

---

## 4. Environment Setup

Copy `.env.example` to create your local `.env` file:

```bash
cp .env.example .env
```

Key configuration parameters:

| Variable | Description | Default / Example |
|---|---|---|
| `ENVIRONMENT` | Application mode | `development` / `production` / `testing` |
| `SECRET_KEY` | Cryptographic secret for signing JWTs | Set to 32+ random characters |
| `DATABASE_URL` | SQLAlchemy async connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/subscription_manager` |
| `REDIS_URL` | Redis broker URL | `redis://localhost:6379/0` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT expiration duration in minutes | `1440` (24 hours) |
| `COOKIE_SECURE` | Enforce HTTPS-only cookie transmission | `False` (in dev), `True` (in prod) |
| `INITIAL_TENANT_NAME` | Reference tenant organization name | `Brightloop Software` |
| `INITIAL_TENANT_SLUG` | Reference tenant organization slug | `brightloop-software` |
| `FIRST_ADMIN_EMAIL` | Default administrator account email | `admin@brightloop.io` |
| `FIRST_ADMIN_PASSWORD` | Default administrator initial password | `Admin@Brightloop123` |

---

## 5. Local Installation

Using `uv` (recommended):

```bash
# 1. Create virtual environment
uv venv

# 2. Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies including dev tools
uv pip install -e ".[dev]"
```

Using standard `pip`:

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

---

## 6. Database Migrations

Apply async database migrations using Alembic:

```bash
# Upgrade database schema to the latest version
python -m alembic upgrade head

# Rollback one migration (if needed)
python -m alembic downgrade -1

# Generate a new migration after model changes
python -m alembic revision --autogenerate -m "Describe migration"
```

---

## 7. Initial Admin & Reference Tenant Seeding

Initialize the reference tenant (**Brightloop Software**) and the primary Admin account:

```bash
python -m app.db.init_db
```

Default credentials:
- **Tenant:** Brightloop Software (`brightloop-software`)
- **Admin Email:** `admin@brightloop.io`
- **Admin Password:** `Admin@Brightloop123`

*(Note: The seeder is idempotent and safe to run multiple times).*

---

## 8. Running the Application

Start the development server with live reload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access the application in your browser:
- **Web UI:** [http://localhost:8000](http://localhost:8000)
- **Interactive API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 9. Docker Compose Startup

To launch the full production-like environment with PostgreSQL, Redis, and FastAPI:

```bash
# Build and start services in the background
docker-compose up -d --build

# Inspect container status and health
docker-compose ps

# View application logs
docker-compose logs -f web

# Stop services
docker-compose down
```

The application automatically applies Alembic migrations and seeds the reference tenant upon container startup.

---

## 10. Running Automated Tests

Run the complete 35-test verification suite covering password policies, JWT authentication, RBAC, tenant isolation, and Jinja2/HTMX web pages:

```bash
python -m pytest -v
```

Run specific test modules:
```bash
python -m pytest tests/test_password.py -v         # Password policy & Argon2id tests
python -m pytest tests/test_auth.py -v             # Login, logout, JWT, password reset
python -m pytest tests/test_rbac.py -v             # Admin, Staff, Customer role permissions
python -m pytest tests/test_tenant_isolation.py -v # Multi-tenant boundary verification
python -m pytest tests/test_web.py -v              # Jinja2 & HTMX web endpoints
```

---

## 11. Available Routes

### Web Interface Routes (Jinja2 + HTMX)

| Method | Path | Description | Access |
|---|---|---|---|
| `GET` | `/` | Redirects to `/dashboard` if logged in, else `/login` | Public |
| `GET` | `/login` | Sign-in page | Public |
| `POST` | `/login` | Form login handler (sets HTTP-only cookie) | Public |
| `GET` | `/register` | Public Customer sign-up page | Public |
| `POST` | `/register` | Form registration handler (creates Customer account) | Public |
| `GET` | `/forgot-password` | Password recovery request & reset form | Public |
| `POST` | `/forgot-password` | Initiates single-use reset token generation | Public |
| `POST` | `/reset-password` | Validates token and updates Argon2id password hash | Public |
| `GET` | `/dashboard` | Authenticated tenant workspace overview | Authenticated |

### API v1 Endpoints (`/api/v1`)

| Method | Path | Description | Auth & RBAC |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Public customer registration | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT token / cookie | Public |
| `POST` | `/api/v1/auth/logout` | Clear authentication cookie | Authenticated |
| `GET` | `/api/v1/auth/me` | Retrieve profile of authenticated user | Authenticated |
| `POST` | `/api/v1/auth/forgot-password` | Request password reset token | Public |
| `POST` | `/api/v1/auth/reset-password` | Submit reset token and set new password | Public |
| `GET` | `/api/v1/admin/users` | List users in current tenant | Admin only |
| `POST` | `/api/v1/admin/staff` | Create a Staff user in current tenant | Admin only |
| `GET` | `/api/v1/customers` | List customer records in current tenant | Staff & Admin |
| `GET` | `/api/v1/customers/{id}` | Get customer by ID (isolated to tenant) | Staff & Admin |
| `POST` | `/api/v1/customers` | Create new customer under current tenant | Staff & Admin |
| `GET` | `/health` | Health check endpoint (application & database) | Public |

---

## 12. Security & Tenant Isolation Architecture

1. **Server-Side Authoritative Tenant Context**: The tenant ID is never trusted from client request bodies or query parameters. The authenticated user's `organization_id` is extracted directly from the verified server-side JWT session.
2. **Scoping on Every Query**: Every database lookup against tenant-owned data filters explicitly by `organization_id`.
3. **URL Tampering Protection**: Accessing `/api/v1/customers/{id}` validates `organization_id == current_user.organization_id`. If the resource belongs to another tenant, a 404 is returned to prevent information disclosure.
4. **Tenant-Partitioned Uniqueness**: Email uniqueness is enforced at the organization level (`UniqueConstraint("organization_id", "email")`), allowing users across separate companies to maintain distinct accounts.
