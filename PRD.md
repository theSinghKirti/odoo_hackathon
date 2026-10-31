# Product Requirements Document (PRD)

## Subscription Manager

**Document status:** Baseline for implementation\
**Project:** Subscription Manager\
**Scope:** Complete subscription-management application as discussed

------------------------------------------------------------------------

## 1. Product overview

Subscription Manager is an application for managing the
subscription-management workflow. The application will provide a
browser-based interface for the Admin, Staff and Customer roles, with
FastAPI serving the application and Jinja2 templates plus HTMX providing
the frontend experience.

The application will cover the modules agreed in the project discussion:

-   User and customer management
-   Product management
-   Subscription plan management
-   Quotations
-   Subscriptions
-   Taxes and discounts
-   Automatic invoices
-   Razorpay payments
-   Renewal automation
-   Dashboard and reports

This document records the agreed scope. It does not define additional
business rules that have not yet been discussed.

## 2. Goals

1.  Provide one application for the agreed subscription-management
    modules.
2.  Support Admin, Staff and Customer roles.
3.  Provide authenticated access and role-based permissions.
4.  Manage products, plans, quotations and subscriptions.
5.  Support taxes, discounts, invoices and Razorpay payment processing.
6.  Support renewal automation.
7.  Provide dashboards and reports.
8.  Keep payment verification on the backend. A browser-side success
    message must not be treated as proof of payment.

## 3. User roles

The roles established in the project discussion are:

### Admin

-   Has administrative access to the application.
-   Can create Staff accounts.
-   Manages users, roles and customer accounts.
-   Access to administrative functionality is controlled by role-based
    permissions.

### Staff

-   Is an application user with permissions assigned according to the
    role/permission foundation.
-   Exact Staff permissions beyond the agreed role-based access model
    remain to be specified.

### Customer

-   Is represented by a customer account.
-   Uses the customer-facing functionality made available by the
    application.
-   Exact customer self-service actions and access boundaries remain to
    be specified.

## 4. Functional scope

### 4.1 Foundation and authentication

-   FastAPI application.
-   PostgreSQL database.
-   SQLAlchemy 2.0 data access.
-   Alembic database migrations.
-   JWT-based authentication.
-   Argon2 password hashing.
-   JWT stored in secure HTTP-only cookies, as established in the
    initial implementation context.
-   Password validation.
-   Admin, Staff and Customer role foundation.

### 4.2 User management

-   Admin-only Staff creation.
-   Role management.
-   Role-based permissions.
-   Customer account management.

### 4.3 Product management

-   Manage products.
-   Product fields, validation rules and product lifecycle rules are not
    yet specified.

### 4.4 Subscription plans

-   Manage subscription plans.
-   Plan pricing and configuration are in scope.
-   Billing intervals, trial rules, proration and plan-change rules have
    not yet been specified.

### 4.5 Quotations

-   Support quotation management.
-   Quotation statuses, expiry rules, conversion rules and approval
    workflow have not yet been specified.

### 4.6 Subscriptions

-   Support subscription management.
-   Subscription lifecycle, renewal dates, cancellation rules,
    pause/resume behavior and billing calculations have not yet been
    specified.

### 4.7 Taxes and discounts

-   Support taxes and discounts.
-   Tax jurisdiction, tax calculation rules, discount types, stacking
    and eligibility rules have not yet been specified.

### 4.8 Automatic invoices

-   Support automatic invoice generation.
-   Invoice numbering, document format, timing, tax presentation and
    adjustment rules have not yet been specified.

### 4.9 Payments

-   Integrate Razorpay as the initial payment provider through a gateway
    integration.
-   Keep the payment gateway behind an application-level integration
    boundary.
-   Perform payment verification on the backend.
-   Never trust a payment-success message from the browser alone.
-   Exact payment methods, retry behavior, refunds, webhook handling and
    reconciliation rules have not yet been specified.

### 4.10 Renewal automation

-   Support automated subscription-renewal work.
-   Celery is the background-job technology and Redis is the message
    broker.
-   Exact scheduling, retry, notification and failure-handling rules
    have not yet been specified.

### 4.11 Dashboard and reports

-   Provide a dashboard and reports.
-   Exact metrics, filters, export formats and report permissions have
    not yet been specified.

## 5. Frontend requirements

-   Use FastAPI with Jinja2 templates to render HTML.
-   Use HTMX for interactive frontend behavior.
-   Do not introduce a separate React application.
-   The frontend communicates with the FastAPI application through its
    application routes.

## 6. Non-functional and technical requirements

-   Use the technology stack recorded in `ARCHITECTURE.md`.
-   Store application data in PostgreSQL.
-   Manage schema changes through Alembic migrations.
-   Hash passwords with Argon2.
-   Use JWT authentication with secure HTTP-only cookies, as established
    in the starter implementation context.
-   Enforce role-based permissions on the backend.
-   Verify payment results on the backend.
-   Use Pytest for automated tests.
-   Use Docker for deployment and local application orchestration.

## 7. Delivery sequence

The agreed implementation sequence is:

1.  Project setup and foundation
2.  Authentication
3.  User management
4.  Product management
5.  Subscription plans
6.  Quotations
7.  Subscriptions
8.  Taxes and discounts
9.  Automatic invoices
10. Razorpay payments
11. Renewal automation
12. Dashboard and reports

The initial project context reports that the foundation and
authentication starter have been created. User management is the next
module proposed for implementation. Their actual completion status must
be confirmed by inspecting and testing the source code.

## 8. Acceptance approach

A module is considered complete only when its functionality is
implemented, connected to the database where applicable, protected by
the required permissions, and covered by relevant Pytest tests.

A file or route existing in the repository is not, by itself, evidence
that a module is complete.

## 9. Open decisions (not to be assumed)

The following details were not established in the project discussion and
must be decided before implementing the affected behavior:

-   Exact fields and validation rules for each business entity.
-   Detailed permission matrix for Admin, Staff and Customer.
-   Product and subscription-plan pricing rules.
-   Subscription billing frequency and lifecycle rules.
-   Quotation workflow and conversion behavior.
-   Tax and discount calculation rules.
-   Invoice numbering and generation timing.
-   Razorpay event, webhook, retry, refund and reconciliation behavior.
-   Renewal scheduling, retry and notification behavior.
-   Dashboard metrics and report definitions.

These are deliberately left open rather than filled with invented
requirements.
