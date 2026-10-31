# AI Development Context

## Subscription Manager (Multi-Tenant SaaS)

**Project Name:** Subscription Manager  
**Platform Style:** Multi-Tenant SaaS with Hypermedia Architecture  
**Frontend Pattern:** FastAPI + Jinja2 Templates + HTMX (Strict: No React / Next.js)  
**Development Methodology:** Incremental, Test-Driven Pair Programming  

---

## 1. Project Overview & Business Domain

Subscription Manager is a unified subscription management, quoting, recurring billing, and invoicing SaaS platform designed to run companies like **Brightloop Software**. It provides:
1. **Catalog with Variants:** Products with name, type, sales/cost price, notes, and attribute variants with price surcharges (e.g., Odoo Brand adds +560 to price), plus toggleable add-ons.
2. **Quotation Engine:** Pre-configured quotation templates valid for a set number of days; sales reps start from templates and convert quotes into live subscriptions.
3. **Subscription Lifecycle:** Rigorous state progression:
   $$\text{Draft} \longrightarrow \text{Quotation} \longrightarrow \text{Confirmed} \longrightarrow \text{Active} \longrightarrow \text{Closed}$$
   with plan-configurable policies for auto-closing, early closure, pausing, and renewing.
4. **Automated Billing Day Invoicing:** Scheduled daily sweeps that generate draft invoices from active subscriptions, compute taxes and discounts, advance billing dates without double-billing or skipping, and progress invoices:
   $$\text{Draft} \longrightarrow \text{Confirmed} \longrightarrow \text{Paid}$$
5. **Tax & Discount Rule Engines:** Admin-configured tax rates and multi-criteria discount rules (fixed amount or %, min spend or quantity, start/end dates, max uses, product vs subscription scope).
6. **Dual Payment Recording:** Internal staff offline payment recording (method, amount, date, note) plus online Razorpay checkout with server-side HMAC signature verification.
7. **Customer Portal:** Dedicated self-service portal (`/portal`) for customers to view own subscriptions and invoices, pause/cancel/renew where allowed, and pay online.
8. **Finance Lead Analytics:** High-performance dashboard (MRR, ARR, active subs, overdue chase list) with a strict requirement that **every page must respond in under 2 seconds** under production load.

---

## 2. Technology Stack & Coding Standards

| Component | Technology | Directives & Restrictions |
| :--- | :--- | :--- |
| **Runtime** | Python 3.12 | Use explicit type hints, async/await patterns, and standard dataclasses/Pydantic models |
| **Web Framework** | FastAPI | Keep route handlers thin; delegate all business logic to service layer |
| **Frontend Templates** | Jinja2 | Clean modular layouts, partial template fragments for HTMX swaps |
| **Frontend Interactivity**| HTMX 1.9+ | Use `hx-get`, `hx-post`, `hx-swap`, `hx-target` for dynamic modals, inline state changes, and live search |
| **Styling** | Vanilla CSS | Tailored, modern design system (Inter font, sleek dark/light accents, micro-animations, glassmorphism) |
| **Database** | PostgreSQL 16+ | Shared DB with tenant `organization_id` column; use `NUMERIC(12, 2)` for money; no float |
| **ORM** | SQLAlchemy 2.0 | Async declarative models; explicit relationship declarations and foreign keys |
| **Migrations** | Alembic | All schema changes must be accompanied by versioned migrations |
| **Task Queue** | Celery + Redis | Asynchronous billing day runs, email dispatch, and auto-close sweeps |
| **Payment Gateway** | Razorpay SDK | Secure online transactions with server-side HMAC-SHA256 signature verification |
| **Testing** | Pytest + HTTPX | Write unit and integration tests covering business rules, state transitions, and multi-tenancy |

> [!WARNING]
> **Prohibited Technologies:**  
> Do **NOT** install or introduce React, Next.js, Vue, or TailwindCSS unless explicitly directed. The frontend stack is strictly **FastAPI + Jinja2 + HTMX**.

---

## 3. User Roles & Permission Model

1. **`Admin`:**
   - Full organization administrative rights.
   - Only role authorized to create Staff accounts.
   - Configures products, variants, add-ons, plans, quotation templates, tax rules, and discount rules.
   - Accesses high-level finance analytics (MRR, ARR, overdue accounts).
2. **`Staff`:**
   - Internal team executing day-to-day operations.
   - Generates quotes from templates, sends quotes, and converts them to subscriptions.
   - Manages subscriptions (pauses, resumes, closes).
   - Confirms, cancels, sends, and prints invoices.
   - Records manual offline payments (Bank Transfer, Cheque, Cash) with method, amount, date, and note.
3. **`Customer`:**
   - External client accessing the Customer Portal (`/portal`).
   - Authenticated with email and strict password ($> 8$ chars, uppercase, lowercase, special char).
   - Views own subscriptions and line items; executes self-service actions (pause, cancel, renew) if permitted by the plan.
   - Views/downloads invoices and executes online payments via Razorpay.

---

## 4. Canonical Project Directory Structure

```text
odoo_hackathon/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_SCHEMA.md
│   ├── BUSINESS_RULES.md
│   ├── API_SPECIFICATION.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── AI_CONTEXT.MD
├── app/
│   ├── core/               # Configuration, security (Argon2id, JWT), database session
│   ├── models/             # SQLAlchemy 2.0 ORM models
│   ├── schemas/            # Pydantic v2 schemas
│   ├── repositories/       # Database query operations with tenant scoping
│   ├── services/           # Domain logic (Billing, Quotes, Subs, Taxes, Discounts, Payments)
│   ├── web/                # Jinja2 template routes (Admin, Staff, Customer Portal)
│   ├── api/v1/             # REST endpoints (Auth, Webhooks, Data Export)
│   ├── templates/          # Jinja2 templates & HTMX partials
│   ├── static/             # Vanilla CSS, SVG icons, client scripts
│   ├── workers/            # Celery worker tasks
│   └── main.py             # ASGI entrypoint
├── migrations/             # Alembic database migrations
├── tests/                  # Pytest test suites
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## 5. Development Guidelines for AI Agents

1. **Check Documentation First:** Refer to `PRD.md`, `BUSINESS_RULES.md`, and `DATABASE_SCHEMA.md` as authoritative domain specifications.
2. **Never Invent Rules:** If a requirement is ambiguous, check the problem statement or ask before making assumptions.
3. **Preserve Multi-Tenancy:** Every repository query must enforce `organization_id` isolation.
4. **Ensure Sub-2-Second Performance:** Use database indexes, limit/offset pagination, and server-side aggregation for reporting.
5. **Write Clean, Idiomatic Code:** Follow PEP 8, use explicit type annotations, and maintain test coverage for all domain logic.