# Product Requirements Document (PRD)

## Subscription Manager (Multi-Tenant SaaS)

**Document Status:** Baseline Specification — Aligned with Problem Statement  
**Project:** Subscription Manager  
**Scope:** Unified subscription and recurring billing SaaS platform running the full lifecycle of product management, quotations, subscriptions, automated invoicing, taxes, discounts, multi-method payments, customer portal, and reporting for organizations like Brightloop Software.

---

## 1. Product Overview

Subscription Manager is a multi-tenant SaaS application that serves as the digital operational backbone for subscription businesses. It enables organizations (such as **Brightloop Software**) to sell business software, add-ons, and physical/digital products with variants, automated recurring billing, quoting, invoicing, offline and online payment recording, and customer self-service.

The application provides a unified, responsive server-rendered interface built with **FastAPI**, **Jinja2 templates**, and **HTMX**, delivering a fast, desktop-class user experience without the complexity of a separate Single Page Application (SPA).

---

## 2. Core Value Proposition & Persona Goals

### 2.1 The Business Problem
Currently, companies run subscriptions via spreadsheets, miss renewals, type invoices by hand, manually reconcile bank payments, and struggle for days to calculate recurring revenue. Subscription Manager replaces manual toil with a single, automated, highly reliable system.

### 2.2 User Roles & Access Boundaries
The application strictly enforces role-based access control across three primary personas:

1. **Admin:**
   - Full control over the organization/system.
   - Creates and manages Staff accounts (only Admins can add Staff).
   - Configures Products, Product Variants, Add-ons, and Subscription Plans.
   - Configures Tax Rules, Discount Rules, and Quotation Templates.
   - Accesses high-level analytics (MRR, ARR, active subscriptions, overdue invoices, revenue).

2. **Staff (Sales, Billing & Support):**
   - Day-to-day operational execution with scoped permissions.
   - Creates quotations using pre-defined Quotation Templates.
   - Converts quotations into subscriptions.
   - Manages subscriptions (tracks status, pauses, resumes, closes).
   - Generates, confirms, cancels, sends, and prints invoices.
   - Manually records offline payments (bank transfer, cheque, cash) with method, amount, date, and note.

3. **Customer:**
   - Accesses a dedicated self-service **Customer Portal**.
   - Authenticates using registered email and secure password.
   - Can view only their own subscriptions and invoices without needing to email staff.
   - Self-manages allowable subscription actions (pause, cancel, renew) as configured by plan rules.
   - Pays invoices online via Razorpay or views recorded offline receipts.

---

## 3. Functional Scope

### 3.1 Organization & Multi-Tenancy Foundation
- Multi-tenant architecture allowing multiple organizations/businesses to operate in isolation on a shared database.
- Every tenant resource (`Product`, `Plan`, `Customer`, `Quotation`, `Subscription`, `Invoice`, `Payment`, `TaxRule`, `DiscountRule`) is strictly scoped by `organization_id`.
- Tenant context is automatically resolved and enforced on all backend queries and HTMX requests.

### 3.2 Authentication & Security
- **Registration & Login:** Secure authentication using JWT stored in HTTP-only, secure, `SameSite=Lax` cookies.
- **Strict Password Rules:** Passwords must be **greater than 8 characters** and contain at least:
  - 1 uppercase letter (`A-Z`)
  - 1 lowercase letter (`a-z`)
  - 1 special character (`!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`)
- **Password Reset:** Automated password reset links sent to the registered email address.
- **Argon2id Hashing:** Password hashing with industry-standard salt and memory-hard configuration.
- **Role-Based Authorization:** Backend dependencies verifying `Admin`, `Staff`, or `Customer` access on every route.

### 3.3 Customer Management
- Maintain customer records: Name, Email (unique per organization), Phone, Company name, Billing Address, Tax/GST ID.
- Customers can be invited to create portal credentials.
- Customers with financial or subscription history cannot be hard-deleted (archived only to preserve legal records).

### 3.4 Product Catalog, Variants & Add-ons
- **Product Entity:**
  - Name, Type (`Software`, `Service`, `Add-on`, `Physical`), Sales Price, Cost Price, Notes, Active status.
- **Product Variants:**
  - Support for multi-variant dimensions (e.g., Brand, Edition, Region).
  - Price Surcharge: Selecting a variant modifies the base price (e.g., selecting the **Odoo Brand** adds **+560** to the sales price).
- **Add-ons:**
  - Configurable add-on products that customers or staff can switch on and off on a subscription.

### 3.5 Subscription Plans
- **Plan Configuration:**
  - Name, Description, Base Price, Currency (`INR`, `USD`, etc.), Minimum Quantity, Availability Date Range (`start_date`, `end_date`).
- **Billing Intervals:** Supported intervals:
  - **Daily**
  - **Weekly**
  - **Monthly**
  - **Yearly**
- **Plan Lifecycle Rules (Admin Configurable per Plan):**
  - `auto_close_on_expiry`: Automatically moves subscription to Closed when expiry date is reached.
  - `allow_early_close`: Allows staff/customer to close early before scheduled period end.
  - `allow_pause`: Allows subscription to be paused.
  - `allow_renewal`: Allows manual or automatic renewal.

### 3.6 Quotation Templates & Quotation Workflow
- **Quotation Templates:**
  - Created by Admin to speed up sales workflows.
  - Contains default plan, pre-configured product lines (products, variants, default quantities), and a default validity period (e.g., valid for 15 or 30 days).
- **Quotation Generation:**
  - Sales reps create offers starting from a quotation template.
  - Assign customer, start date, expiry date (based on validity days), and payment terms.
  - Custom line items showing Product, Variant, Quantity, Unit Price, Taxes, Discounts, and Net Line Amount.
- **Quotation Conversion:**
  - Can be sent or printed as a quotation offer.
  - Customer accepts or staff confirms, converting the quotation directly into a `Subscription`.

### 3.7 Subscriptions & State Machine
- **Subscription Properties:**
  - Unique subscription identifier (e.g., `SUB-2026-0001`).
  - Customer reference, Plan reference, Start date, Expiry date, Next billing date, Payment terms.
  - Line items: Product, Variant, Quantity, Unit price, Applied tax, Line total.
- **Subscription Lifecycle States:**
  $$\text{Draft} \longrightarrow \text{Quotation} \longrightarrow \text{Confirmed} \longrightarrow \text{Active} \longrightarrow \text{Closed}$$
  - **Draft:** Newly created offer being drafted by staff.
  - **Quotation:** Finalized quote sent to the customer, awaiting confirmation.
  - **Confirmed:** Customer agreed; pending initial activation/billing.
  - **Active:** Live subscription entitled to service, recurring invoices generated on billing intervals.
  - **Paused:** Temporarily suspended (no invoicing, service paused).
  - **Closed:** Final state (reached on expiry date, early termination, or non-renewal).

### 3.8 Automated Invoicing & "Billing Day" Execution
- **Billing Day Automation:**
  - Automated worker (Celery + Redis) processes all active subscriptions whose `next_billing_date <= today`.
  - Generates an `Invoice` containing customer details, product lines, active taxes, discounts, and line totals.
  - Advances subscription `next_billing_date` based on interval (daily, weekly, monthly, yearly).
  - **Billing Safety Invariants:** Strict idempotency to guarantee **nothing is billed twice or skipped**.
- **Invoice Properties & Actions:**
  - Unique sequential invoice number (e.g., `INV-2026-0001`).
  - Staff actions: **Confirm**, **Cancel**, **Send (Email)**, or **Print (Download PDF)**.
- **Invoice Lifecycle States:**
  $$\text{Draft} \longrightarrow \text{Confirmed} \longrightarrow \text{Paid}$$
  - (Also supports `Cancelled` / `Void`).

### 3.9 Tax Rules Engine
- Admin configures tax rules: Rule Name (e.g., `GST 18%`, `VAT 20%`), Rate percentage, Tax Code, Active status.
- Taxes calculate automatically on quotation lines, subscription lines, and generated invoices.

### 3.10 Discount Rules Engine
- Admin creates promotional and volume discount rules:
  - Discount Type: **Fixed Amount** (e.g., ₹500 off) or **Percentage** (e.g., 10% off).
  - Qualification Criteria: **Minimum Purchase Amount** or **Minimum Quantity** (e.g., taking $> 10$ seats).
  - Duration: Start Date and End Date.
  - Usage Limits: Maximum number of times the discount can be used across the system (`max_uses`) and tracking `times_used`.
  - Applicability Scope: **Specific Products** or **Whole Subscriptions**.
- **Automatic Application & Expiry:**
  - When applicable to a subscription, the discount appears automatically on the next invoice without manual staff intervention.
  - Automatically ceases to apply when expired by date or when maximum uses are exhausted.

### 3.11 Payments: Offline Multi-Method & Online Gateway
- **Multi-Method Offline Recording:**
  - Payments arriving by different methods (Bank Transfer, Cheque, Cash, NEFT/RTGS) on different days.
  - Staff records payment against the invoice: **Payment Method, Amount, Date, and Note**.
- **Razorpay Online Integration:**
  - Customers in the portal can pay outstanding invoices online via Razorpay.
  - Verification is performed strictly on the backend via HMAC-SHA256 signature verification (`razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`).
  - Browser-side success messages are **never** trusted as proof of payment.
  - Webhooks handle asynchronous captures and refunds with idempotent event recording.
- **Invoice Reconciliation:**
  - Invoices track `amount_paid` and `amount_due`.
  - Once `amount_paid >= total_amount`, invoice automatically moves to **`Paid`**.
  - Outstanding and overdue invoices are tracked with due dates to chase overdue revenue.

### 3.12 Customer Self-Service Portal
- Dedicated `/portal` routes for authenticated customers.
- Customers view:
  - Current active subscriptions, next billing dates, and subscription line details.
  - Self-service controls: pause, resume, cancel, or renew where permitted by the plan configuration.
  - Invoices list with statuses (`Confirmed`, `Paid`, `Overdue`), PDF download, and online payment button.
  - No access to internal staff records, cost prices, or other customers' data.

### 3.13 Finance Lead Analytics & Dashboard
- Dedicated executive overview for Finance Lead & Admin:
  - **Active Subscriptions Count**
  - **Monthly Recurring Revenue (MRR)** & **Annual Recurring Revenue (ARR)**
  - **Payments Collected** (total received in period)
  - **Outstanding & Overdue Invoices** (amount owed, overdue count)
- Advanced filters by date range, customer, plan, and status.
- Summary tables with quick actions to chase overdue invoices.

---

## 4. Non-Functional Requirements (NFR)

1. **Performance & Latency:**
   - **Under 2 Seconds Response Time:** Every page, filter, and analytical summary view must respond in **under 2 seconds**, even with thousands of subscriptions on the books.
   - Database queries must use proper indexes on `organization_id`, `status`, `next_billing_date`, `customer_id`, and foreign keys.
2. **Frontend Architecture:**
   - Server-rendered HTML using **FastAPI** + **Jinja2**.
   - Interactive components (modals, pagination, tab switching, inline filtering, payment status updates) powered by **HTMX**.
   - No separate React or Next.js build step.
3. **Financial Integrity:**
   - Strict decimal arithmetic for all monetary values (`Numeric(12, 2)` or integer minor units). Floating-point math is strictly forbidden.
   - Immutable financial history: Paid invoices and recorded payments cannot be silently altered or deleted.
4. **Data Isolation:**
   - Multi-tenant query isolation enforced at the service and repository level on every database operation.

---

## 5. Delivery Milestones

1. **Phase 1: Foundation & Auth** — Multi-tenant organization model, User model, Argon2id auth, session cookies, password validation (>8 chars, uppercase, lowercase, special char), reset link flow, base Jinja2/HTMX layout.
2. **Phase 2: Product & Plan Catalog** — Products (sales/cost price, notes), Product Variants (price surcharges, e.g. Odoo brand +560), Add-ons, Subscription Plans (daily, weekly, monthly, yearly, auto-close, pause, renew toggles).
3. **Phase 3: Tax & Discount Rules Engine** — Admin tax configuration, Admin discount rules (fixed/%, min qty/spend, dates, max uses, product vs subscription scope).
4. **Phase 4: Quotation Templates & Quotations** — Quotation templates, quotation creation, quotation lines, expiry, and conversion to subscription.
5. **Phase 5: Subscriptions & Lifecycle** — Subscription numbering, lines, lifecycle states (`Draft → Quotation → Confirmed → Active → Closed`), pause/resume/close logic.
6. **Phase 6: Billing Automation & Invoicing** — Billing day automated generation, line item copy, tax/discount calculation, invoice states (`Draft → Confirmed → Paid`), actions (confirm, cancel, send, print PDF).
7. **Phase 7: Multi-Method Payments & Razorpay** — Staff offline payment recording (method, amount, date, note) and customer online Razorpay checkout with backend signature verification.
8. **Phase 8: Customer Self-Service Portal** — Dedicated customer portal views for subscriptions, invoices, PDF downloads, and online payments.
9. **Phase 9: Finance Dashboard & Performance Optimization** — Executive dashboard (MRR, ARR, active subs, overdue chase list), query optimization to ensure <2s response times under load.
