# Implementation Plan — Subscription Manager (Team Work-Split)

**Project:** Subscription Manager  
**Platform Style:** Multi-Tenant SaaS with Hypermedia Architecture  
**Frontend Pattern:** FastAPI + Jinja2 Templates + HTMX (Tailored Vanilla CSS)  
**Development Structure:** Two-Track Parallel Development (Backend vs Frontend)  
**Status:** Approved Roadmap for Two Collaborating Developers  

---

## 1. Team Ownership & Responsibilities

To enable seamless parallel development without merge conflicts or blocking dependencies, the codebase and responsibilities are split between two developers:

```
                                  INTEGRATION BOUNDARY
                                (app/web/ & HTMX Contracts)
                                             │
      ┌──────────────────────────────────────┴──────────────────────────────────────┐
      │                                                                             │
      ▼                                                                             ▼
DEVELOPER 1 (BACKEND TRACK)                                           DEVELOPER 2 (FRONTEND TRACK)
• Database Models (SQLAlchemy 2.0)                                    • Base HTML Layouts & Shells (Jinja2)
• Alembic Migrations & PostgreSQL                                     • Tailored Design System (Vanilla CSS)
• Business Logic Services & Domain Engines                            • Component Templates (Modals, Cards, Tables)
• Repositories & Database Queries                                     • HTMX Interactivity (hx-get, hx-post, hx-swap)
• REST API Endpoints (/api/v1/...)                                    • Form Validations & Client-side UX
• Celery Workers & Redis Billing Sweeps                               • Responsive Design & Micro-animations
• Razorpay Server-side HMAC Verification                              • Portal & Staff Dashboard Templates
• Backend Automated Pytest Suite                                      • Mock Data Contexts for Template Preview
```

### Directory Ownership Matrix

| Directory / File Area | Primary Owner | Secondary / Consumer | Responsibility |
| :--- | :--- | :--- | :--- |
| `app/models/` | **Dev 1 (Backend)** | None | Database table schemas, ORM relationships, constraints |
| `app/repositories/` | **Dev 1 (Backend)** | Dev 1 | Database query encapsulation, tenant isolation filters |
| `app/services/` | **Dev 1 (Backend)** | Dev 2 | Core business logic (Billing, Taxes, Discounts, Quotes) |
| `app/api/v1/` | **Dev 1 (Backend)** | Dev 2 / External | JSON REST APIs, Webhook receivers, Data exports |
| `app/workers/` | **Dev 1 (Backend)** | None | Celery tasks for recurring billing runs and background jobs |
| `migrations/` | **Dev 1 (Backend)** | None | Alembic migration scripts |
| `app/templates/` | **Dev 2 (Frontend)** | Dev 1 | All Jinja2 template files, layouts, and HTMX partials |
| `app/static/` | **Dev 2 (Frontend)** | None | Vanilla CSS design tokens, icons, and minimal JS scripts |
| `app/web/` | **Shared / Handshake** | Both | FastAPI view routers: Dev 1 connects services; Dev 2 injects template contexts |

---

## 2. Parallel Milestone Roadmap

### Track A: Developer 1 — Backend Engineering

#### Milestone B1: Foundation, Multi-Tenancy & Authentication Core
- [ ] Initialize Python virtual environment with `uv` or `pip` (`pyproject.toml`).
- [ ] Configure PostgreSQL async engine with SQLAlchemy 2.0 and Alembic.
- [ ] Create database models: `Organization`, `User` (Role ENUM: `admin`, `staff`, `customer`), `Customer`.
- [ ] Implement password security validator (> 8 chars, uppercase, lowercase, special char).
- [ ] Implement Argon2id password hashing and JWT cookie issuance/validation.
- [ ] Implement Password Reset token generation and verification services.
- [ ] Implement multi-tenant dependency `get_current_tenant` to enforce `organization_id` on all queries.
- [ ] Setup Docker Compose for PostgreSQL 16 and Redis 7.

#### Milestone B2: Product Catalog & Variant Surcharge Engine
- [ ] Create `Product` model (Software, Service, Add-on, Physical; sales price, cost price, notes).
- [ ] Create `ProductVariant` model (attribute name, value, price surcharge, SKU).
- [ ] Build `ProductService` with dynamic surcharge calculation (e.g., Odoo Brand adds +560).
- [ ] Build repository queries for catalog listing, variant retrieval, and add-on toggling.

#### Milestone B3: Plans & Lifecycle Policies Backend
- [ ] Create `SubscriptionPlan` model with intervals (`daily`, `weekly`, `monthly`, `yearly`).
- [ ] Store policy toggles: `auto_close_on_expiry`, `allow_early_close`, `allow_pause`, `allow_renewal`.
- [ ] Build `PlanService` validating minimum quantity and date availability window (`available_from`, `available_until`).

#### Milestone B4: Tax & Discount Calculation Engines
- [ ] Create `TaxRule` model (name, rate percentage, active status).
- [ ] Create `DiscountRule` model (fixed/%, min spend/qty, dates, max uses, product/subscription scope).
- [ ] Build `TaxEngine` to compute line-level and total taxes.
- [ ] Build `DiscountEngine` to check eligibility, apply discounts, and atomically increment `times_used`.

#### Milestone B5: Quotation & Atomic Conversion Service
- [ ] Create `QuotationTemplate` and `QuotationTemplateLine` models (validity days, lines).
- [ ] Create `Quotation` and `QuotationLine` models (`QUO-YYYY-XXXX` numbering, customer, expiry date).
- [ ] Build `QuotationService` to calculate expiry date and quote totals with taxes and discounts.
- [ ] Build **Atomic Conversion Service**: converts confirmed quote into a live `Subscription` in one transaction.

#### Milestone B6: Subscription State Machine
- [ ] Create `Subscription` and `SubscriptionLine` models (`SUB-YYYY-XXXX`).
- [ ] Implement state machine transitions: `Draft → Quotation → Confirmed → Active → Closed`.
- [ ] Implement `pause_subscription()`, `resume_subscription()`, and `close_subscription()` services enforcing plan policies.

#### Milestone B7: Automated Billing Day & Invoicing Worker
- [ ] Create `Invoice` and `InvoiceLine` models (`INV-YYYY-XXXX`, `Draft → Confirmed → Paid`).
- [ ] Configure Celery with Redis broker for background scheduling.
- [ ] Implement idempotent Billing Sweep task using `SELECT ... FOR UPDATE SKIP LOCKED`:
  - Finds active subscriptions where `next_billing_date <= today`.
  - Generates invoice, computes taxes/discounts, advances `next_billing_date`, and records `last_billed_date`.
- [ ] Implement invoice actions: `confirm_invoice()`, `cancel_invoice()`.

#### Milestone B8: Multi-Method Payment Ledger & Razorpay Integration
- [ ] Create `Payment` model (method, amount, payment date, note, status, Razorpay IDs).
- [ ] Build Offline Payment service: records manual payments (Bank Transfer, Cheque, Cash), decrements `amount_due`, and marks invoice `Paid` when balance is 0.
- [ ] Integrate Razorpay SDK: order creation and server-side HMAC-SHA256 signature verification.
- [ ] Build webhook handler with duplicate event prevention.

#### Milestone B9: Reporting & Analytical Aggregations
- [ ] Build `AnalyticsService` executing raw SQL aggregations:
  - Active subscriptions count.
  - MRR & ARR calculation across daily, weekly, monthly, and yearly intervals.
  - Total collected revenue in period.
  - Overdue invoices count and total amount.
- [ ] Apply database covering indexes to guarantee query execution in $< 50\text{ ms}$.

#### Milestone B10: Backend Test Suite & Isolation Verification
- [ ] Write unit tests for variant math, discount limits, and password validation.
- [ ] Write integration tests for billing runs, quotation conversion, and Razorpay signature checks.
- [ ] Write multi-tenant isolation tests (verifying Org A cannot read Org B).

---

### Track B: Developer 2 — Frontend & UI/UX Engineering

#### Milestone F1: Core Design System & Base Templates
- [ ] Create `app/static/css/main.css` tailored design system:
  - Color palette: Modern dark/light accents, professional slate, crisp borders, status badges (Active=green, Paused=amber, Closed=slate, Overdue=red).
  - Typography: Google Font Inter, clean hierarchy, legible data tables.
  - Micro-animations: Smooth hover states, modal fade-ins, loading spinners for HTMX requests (`.htmx-indicator`).
- [ ] Build `app/templates/base.html` shell with responsive sidebar navigation, top bar, user dropdown, and toast notification container.
- [ ] Include HTMX 1.9+ library and configure global headers (`X-Requested-With`, CSRF/Cookie handling).
- [ ] Build Authentication screens:
  - Login page (`login.html`) with smooth focus states and error banners.
  - Registration page (`register.html`) with real-time password strength / requirement indicator (>8 chars, upper, lower, special).
  - Forgot Password & Reset Password pages.

#### Milestone F2: Product Catalog & Variant Manager Views
- [ ] Build Product Catalog page (`templates/admin/products.html`):
  - Filter bar (filter by Software, Service, Add-on, Physical).
  - Live search input using `hx-get` with debounce (`hx-trigger="keyup changed delay:300ms"`).
  - Responsive table showing name, type, sales price, cost price, and status badge.
- [ ] Build Create/Edit Product Modal (`partials/product_form.html`).
- [ ] Build Product Variant Manager component (`partials/variant_manager.html`):
  - Dynamic rows to add attribute name (e.g. Brand), value (e.g. Odoo), and price surcharge input (+560).
  - Real-time preview of effective sales price.

#### Milestone F3: Subscription Plan Management Views
- [ ] Build Plan Cards grid view (`templates/admin/plans.html`):
  - Clean cards showing interval badge (Daily, Weekly, Monthly, Yearly), base price, and availability dates.
  - Visual policy indicator chips: Auto-close, Early close, Pause allowed, Renew allowed.
- [ ] Build Plan Editor modal (`partials/plan_form.html`) with toggle switches for lifecycle policies.

#### Milestone F4: Tax & Discount Rules Configuration UI
- [ ] Build Tax Rules table view (`templates/admin/taxes.html`) with quick create/toggle modal.
- [ ] Build Discount Rules view (`templates/admin/discounts.html`):
  - Filter by active/expired.
  - Form supporting fixed amount vs percentage, min spend/qty triggers, start/end datepickers, max uses limit, and product scope selector.
  - Visual progress bar showing usage (`times_used` / `max_uses`).

#### Milestone F5: Quotation Builder & Template Selector
- [ ] Build Quotation Template Manager (`templates/admin/quotation_templates.html`).
- [ ] Build Sales Quotation Form (`templates/staff/quotation_form.html`):
  - "Start from Template" dropdown that pre-populates product lines and validity days.
  - Dynamic line item table: add/remove product, select variant, adjust quantity.
  - Live summary card: Subtotal, Tax breakdown, Discount breakdown, and Total Amount.
- [ ] Build Quotation Detail View (`templates/staff/quotation_detail.html`):
  - Action buttons: "Send to Customer", "Print Quotation (Clean Print CSS)", and "Convert to Subscription".

#### Milestone F6: Subscriptions Management Dashboard
- [ ] Build Subscriptions List view (`templates/staff/subscriptions.html`):
  - Status tab filters (`All`, `Active`, `Draft`, `Paused`, `Closed`).
  - Table showing Subscription Number, Customer, Plan, Next Billing Date, and Amount.
- [ ] Build Subscription Detail View (`templates/staff/subscription_detail.html`):
  - Visual status progress bar: `Draft → Quotation → Confirmed → Active → Closed`.
  - HTMX inline action buttons: Pause, Resume, Close, Renew (triggers inline modal confirmation and partial swap).
  - Tab for line items and attached Add-ons (toggle on/off).

#### Milestone F7: Invoices Management & Printable Invoice View
- [ ] Build Invoices List view (`templates/staff/invoices.html`):
  - Filter tabs: `Draft`, `Confirmed`, `Paid`, `Overdue`.
  - Color-coded status badges and due dates.
- [ ] Build Invoice Detail & Printable View (`templates/staff/invoice_detail.html`):
  - Clean, professional invoice layout matching Brightloop Software branding.
  - Dedicated print stylesheet (`@media print`) for pixel-perfect PDF export via browser print.
  - Action buttons: "Confirm Invoice", "Cancel Invoice", "Send via Email", "Record Payment".

#### Milestone F8: Multi-Method Payment Modal & Razorpay Checkout UI
- [ ] Build "Record Offline Payment" modal (`partials/payment_modal.html`):
  - Fields for Payment Method (Bank Transfer, Cheque, Cash), Amount, Date, and Reference Note.
  - HTMX submission updating invoice balance and status badge without page reload.
- [ ] Build Customer Online Checkout modal:
  - Razorpay checkout modal launcher script.
  - Success/Failure feedback overlays.

#### Milestone F9: Dedicated Customer Portal (`/portal`)
- [ ] Build Customer Portal Layout (`templates/portal/layout.html`):
  - Simplified, customer-friendly navigation (Subscriptions, Invoices, Profile).
  - Restricted context: displays only the authenticated customer's records.
- [ ] Build Customer Dashboard (`templates/portal/dashboard.html`):
  - Summary card: Active subscriptions and upcoming renewals.
  - Customer Subscriptions view with self-service Pause/Cancel controls (if permitted by plan).
  - Customer Invoices view with "Download PDF" and "Pay Online" buttons.

#### Milestone F10: Finance Lead Analytics Dashboard
- [ ] Build Finance Overview (`templates/admin/finance_dashboard.html`):
  - Metric stat cards: Active Subscriptions, Monthly Recurring Revenue (MRR), Annual Recurring Revenue (ARR), Total Collected Revenue.
  - Overdue Invoices chase table: Customer name, overdue days, amount due, and "Chase / Send Reminder" action.
  - Date range and interval filter bar using HTMX partial swaps to keep responses snappy (< 2 seconds).

---

## 3. Integration & Sync Points (Contracts Between Dev 1 & Dev 2)

| Sync Point | Feature Domain | Backend Deliverable (Dev 1) | Frontend Deliverable (Dev 2) | Handshake Contract |
| :---: | :--- | :--- | :--- | :--- |
| **Sync 1** | **Auth & Shell** | Auth cookies, session dependency, login/register API endpoints | `base.html`, `login.html`, `register.html`, CSS system | Form POST to `/auth/login`, redirects to `/staff/dashboard` or `/portal` |
| **Sync 2** | **Catalog & Plans** | Models & Services for Products, Variants (+560), and Plans | Catalog table, Product modal, Plan cards, Variant rows | HTMX `GET /web/products` returning `<tbody>` rows; `POST /web/products` |
| **Sync 3** | **Quoting & Conversion**| Template models, Quote calculation & conversion service | Quote form, template pre-filler, quote detail page | `POST /web/quotes/{id}/convert` returns updated sub status badge |
| **Sync 4** | **Subs & Lifecycle** | Subscription state machine (pause/resume/close/renew) | Subscriptions table, detail view with HTMX action buttons | HTMX `POST /web/subs/{id}/pause` returns swapped `#sub-status-badge` |
| **Sync 5** | **Billing & Invoices**| Celery billing task, invoice generator, tax/discount logic | Invoices table, invoice detail page, print CSS template | `GET /web/invoices/{id}` renders invoice; `POST /confirm` swaps badge |
| **Sync 6** | **Payment Processing**| Offline recording endpoint + Razorpay verify API | Record payment modal + Razorpay frontend launch script | `POST /web/invoices/{id}/payments` updates balance in `#invoice-totals` |
| **Sync 7** | **Customer Portal** | Portal data endpoints filtered strictly by `customer_id` | Portal layout, sub cards, invoice list, pay button | Route `/portal/...` isolated from internal staff views |
| **Sync 8** | **Finance Dashboard**| Fast aggregate service (MRR, ARR, overdue accounts) | Metric stat cards, overdue chase table, date filter | `GET /web/finance/summary` renders within $< 2\text{s}$ |

---

## 4. How to Work in Parallel Without Blocking Each Other

1. **Frontend Mocking:** Developer 2 can build and refine Jinja2 templates and Vanilla CSS by passing mock dictionaries in temporary view routes before Developer 1 finishes the database services.
2. **Backend Headless Testing:** Developer 1 can write, test, and verify all domain logic (variant math, billing sweeps, tax calculations, Razorpay signatures) via Pytest without waiting for HTML templates.
3. **Merging at `app/web/`:** When both tracks are ready for a milestone, Developer 1 plugs the domain service into the route handler, and Developer 2 ensures the template consumes the real context variables.