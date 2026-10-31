# Implementation Plan — Subscription Manager

**Project:** Subscription Manager  
**Platform Type:** Multi-Tenant SaaS with Hypermedia Architecture  
**Frontend Pattern:** FastAPI + Jinja2 Templates + HTMX (No React / Next.js)  
**Status:** Approved Roadmap & Milestone Breakdown  

---

## 1. Architectural Stack Confirmation

- **Backend:** Python 3.12, FastAPI, Pydantic v2
- **Database:** PostgreSQL 16+, SQLAlchemy 2.0 (Async/Declarative), Alembic migrations
- **Frontend:** Jinja2 HTML Templates, HTMX 1.9+, Vanilla CSS (Tailored Design System)
- **Background Tasks:** Celery + Redis (Message broker & task result store)
- **Payments:** Multi-Method Offline Recording + Razorpay Online Gateway
- **Testing:** Pytest, HTTPX, Pytest-Asyncio
- **Deployment:** Docker, Docker Compose

---

## 2. Milestone Phases Breakdown

### Phase 0 — Documentation & Architectural Alignment *(Completed)*
- [x] Align PRD with Odoo Hackathon Problem Statement.
- [x] Establish Multi-Tenant SaaS model with Brightloop Software reference tenant.
- [x] Standardize frontend on FastAPI + Jinja2 + HTMX.
- [x] Define Admin, Staff, and Customer RBAC model.
- [x] Formalize full Product/Variant, Quotation, Subscription, Invoicing, Tax, and Discount rules.

---

### Phase 1 — Project Foundation, Multi-Tenant Database & Auth
**Objective:** Set up project scaffolding, database models, and strict RBAC authentication.
- [ ] Initialize Python environment using `uv` or `pip`.
- [ ] Configure FastAPI app instance, Jinja2 template loader, and static assets directory.
- [ ] Set up PostgreSQL async engine with SQLAlchemy 2.0 and Alembic.
- [ ] Implement database models:
  - `Organization`
  - `User` (Role ENUM: `admin`, `staff`, `customer`)
  - `Customer`
- [ ] Implement password security validator:
  - Length $> 8$ characters, at least 1 uppercase, 1 lowercase, 1 special character.
- [ ] Implement Argon2id password hashing and JWT authentication in HTTP-only cookies.
- [ ] Implement Password Reset flow (token generation, email dispatch simulation, password update).
- [ ] Create base HTML layout (`base.html`) with HTMX integration, header navigation, and flash message toasts.
- [ ] Setup Docker Compose for PostgreSQL and Redis.

---

### Phase 2 — Product Catalog, Variants & Add-ons
**Objective:** Enable Admins to configure products, variants with price surcharges, and add-ons.
- [ ] Implement `Product` model (Name, Type: Software/Service/Addon/Physical, Sales Price, Cost Price, Notes).
- [ ] Implement `ProductVariant` model (Attribute Name, Attribute Value, Price Extra, SKU).
- [ ] Implement Variant price computation logic (e.g. Odoo brand adds +560 to base price).
- [ ] Build Admin UI views (Jinja2 + HTMX):
  - Product catalog list with search and filters.
  - Create / edit product modal.
  - Variant manager with dynamic surcharge inputs.
- [ ] Implement Add-on toggle logic for subscriptions.

---

### Phase 3 — Subscription Plans & Lifecycle Configuration
**Objective:** Allow Admins to create plans with billing intervals and policy toggles.
- [ ] Implement `SubscriptionPlan` model:
  - Intervals: `daily`, `weekly`, `monthly`, `yearly`.
  - Base price, currency, min quantity, date availability range.
  - Lifecycle toggles: `auto_close_on_expiry`, `allow_early_close`, `allow_pause`, `allow_renewal`.
- [ ] Build Admin Plan Management views (Jinja2 + HTMX):
  - Plan card list with status badges.
  - Create / edit plan form with interval selector and permission toggles.

---

### Phase 4 — Tax & Discount Rules Engines
**Objective:** Provide automated rule engines for taxes and multi-tiered promotional discounts.
- [ ] Implement `TaxRule` model (Name, Rate percentage, Active status).
- [ ] Implement `DiscountRule` model:
  - Type: `fixed_amount` or `percentage`.
  - Qualification: `min_purchase_amount` or `min_quantity`.
  - Date validity: `start_date`, `end_date`.
  - Limits: `max_uses`, `times_used`.
  - Scope: `product` or `subscription`.
- [ ] Build Admin interfaces for Tax and Discount configuration.
- [ ] Unit test discount evaluation, qualification triggers, and usage depletion.

---

### Phase 5 — Quotation Templates & Quotation Conversion
**Objective:** Accelerate sales offers using templates and quote-to-subscription conversion.
- [ ] Implement `QuotationTemplate` and `QuotationTemplateLine` models (validity days, default plan, product lines).
- [ ] Implement `Quotation` and `QuotationLine` models (`QUO-YYYY-XXXX` numbering, customer, expiry date, payment terms).
- [ ] Build Sales / Staff Quotation workflow:
  - Template selection and quote generation.
  - Dynamic line item editing with live tax and discount computation.
  - Status progression: `Draft → Quotation → Confirmed`.
  - **Convert to Subscription:** Atomic conversion service transforming confirmed quote into an active Subscription.

---

### Phase 6 — Subscriptions Engine & State Transitions
**Objective:** Deliver the operational subscription backbone for managing customer agreements.
- [ ] Implement `Subscription` and `SubscriptionLine` models (`SUB-YYYY-XXXX`).
- [ ] Implement Subscription state machine:
  $$\text{Draft} \longrightarrow \text{Quotation} \longrightarrow \text{Confirmed} \longrightarrow \text{Active} \longrightarrow \text{Closed}$$
- [ ] Implement Pause, Resume, Close, and Renewal actions with plan policy verification.
- [ ] Build Staff Subscriptions list and detail views with HTMX state transition buttons.

---

### Phase 7 — Automated Billing Day & Invoicing
**Objective:** Automate recurring invoice generation on billing days with strict idempotency.
- [ ] Implement `Invoice` and `InvoiceLine` models (`INV-YYYY-XXXX`, `Draft → Confirmed → Paid`).
- [ ] Implement automated Billing Day worker (Celery task):
  - Queries active subscriptions due on or before `CURRENT_DATE`.
  - Row-level lock (`SKIP LOCKED`) to prevent double-billing.
  - Generates invoice, computes taxes and discounts, and advances `next_billing_date`.
- [ ] Implement Staff invoice actions: Confirm, Cancel, Send (Email simulation), and Print (Clean HTML/PDF download).

---

### Phase 8 — Multi-Method Offline Payments & Razorpay Online Gateway
**Objective:** Reconcile payments received offline and process online customer payments.
- [ ] Implement `Payment` model (method, amount, payment date, note, Razorpay order/payment IDs).
- [ ] Build Staff Offline Payment Recording modal:
  - Select invoice, input method (Bank Transfer, Cheque, Cash), amount, date, and note.
  - Automatically updates invoice `amount_due` and marks `Paid` when balance is zero.
- [ ] Implement Razorpay backend integration:
  - Create Razorpay Order endpoint.
  - HMAC-SHA256 signature verification service.
  - Razorpay Webhook receiver with idempotency log.

---

### Phase 9 — Customer Self-Service Portal
**Objective:** Dedicated portal for customers to view and manage their subscriptions and invoices.
- [ ] Implement `/portal` router and customer portal base layout.
- [ ] Customer Dashboard:
  - Active subscriptions overview with next renewal dates.
  - Self-service controls: Pause, Resume, Renew (conditioned on plan settings).
- [ ] Invoices list:
  - Status badges (`Confirmed`, `Paid`, `Overdue`).
  - Download PDF button.
  - "Pay Online" modal integrating Razorpay Checkout.

---

### Phase 10 — Finance Lead Dashboard & Performance Optimization
**Objective:** Provide end-of-month financial metrics and ensure sub-2-second response times under load.
- [ ] Implement Finance Summary view:
  - Active subscriptions count.
  - MRR & ARR calculations.
  - Payments collected in period.
  - Overdue invoices chase list sorted by age.
- [ ] Database optimization:
  - Apply covering indexes for billing sweeps, customer lookups, and overdue invoices.
  - Implement server-side pagination with HTMX partial table swaps.
- [ ] Benchmark response times with 5,000+ mock subscriptions to verify $< 2\text{s}$ execution.

---

### Phase 11 — Testing & Verification
- [ ] Unit tests for variant surcharge math, discount depletion, and password validation.
- [ ] Integration tests for the full billing day cycle.
- [ ] Tenant isolation test: Verify Organization A cannot access Organization B's records.
- [ ] Role authorization test: Verify Customers cannot access Staff/Admin routes.