# System Architecture

## Subscription Manager

**Document status:** Baseline for implementation\
**Architecture status:** Selected stack recorded as agreed

------------------------------------------------------------------------

## 1. Architecture overview

Subscription Manager will be a server-rendered web application.

FastAPI is the backend framework and application server. Jinja2 renders
HTML templates, while HTMX provides interactive frontend behavior.
PostgreSQL stores application data. SQLAlchemy 2.0 is the ORM, and
Alembic manages database migrations.

Authentication uses JWT and Argon2. Celery runs background jobs with
Redis as its message broker. Razorpay is the initial payment provider,
integrated through a gateway boundary. Pytest is used for testing, and
Docker is used for deployment.

A separate React frontend is not part of the selected architecture.

## 2. Technology stack

  Layer             Selected technology
  ----------------- -------------------------
  Backend           FastAPI
  Frontend          FastAPI + Jinja2 + HTMX
  Database          PostgreSQL
  ORM               SQLAlchemy 2.0
  Migrations        Alembic
  Authentication    JWT + Argon2
  Background jobs   Celery
  Message broker    Redis
  Payment gateway   Razorpay integration
  Testing           Pytest
  Deployment        Docker

## 3. Application layers and responsibilities

### 3.1 Presentation layer

-   Jinja2 templates render application pages.
-   HTMX provides interactive page behavior.
-   The browser interacts with FastAPI routes.
-   Authentication tokens are stored in secure HTTP-only cookies, as
    established in the initial implementation context.

### 3.2 Application/backend layer

-   FastAPI exposes application routes and API endpoints.
-   Backend application logic implements the agreed modules.
-   Backend routes enforce authentication and role-based permissions.
-   Payment verification is performed on the backend.

### 3.3 Data-access layer

-   SQLAlchemy 2.0 maps application entities to PostgreSQL.
-   Database access is performed through the ORM.
-   Alembic manages schema changes through versioned migrations.

### 3.4 Background-processing layer

-   Celery executes background jobs.
-   Redis acts as the Celery message broker.
-   Renewal automation is the agreed background-processing use case.
-   Detailed job schedules and retry policies remain to be specified.

### 3.5 Payment integration layer

-   Razorpay is the initial payment provider.
-   Payment integration is kept behind a gateway abstraction.
-   Provider-specific interaction should remain separate from
    subscription-management business logic.
-   Payment success must be verified by the backend. Browser-provided
    success state is not authoritative.

## 4. Logical module boundaries

The application scope is divided into these modules:

1.  Authentication
2.  User management
3.  Customer account management
4.  Product management
5.  Subscription-plan management
6.  Quotations
7.  Subscriptions
8.  Taxes and discounts
9.  Automatic invoices
10. Razorpay payment integration
11. Renewal automation
12. Dashboard and reports

These are logical responsibilities within the selected application
architecture. This document does not prescribe additional services or
infrastructure.

## 5. Role and access foundation

The roles established are:

-   Admin
-   Staff
-   Customer

The backend is responsible for enforcing role-based permissions.
Admin-only Staff creation is an agreed requirement. The complete
permission matrix for the remaining actions is not yet defined and must
not be inferred.

## 6. Request and processing flows

### 6.1 Server-rendered application request

1.  A user requests an application page.
2.  FastAPI receives the request.
3.  Authentication and authorization are checked where required.
4.  The application obtains or updates data through SQLAlchemy.
5.  FastAPI renders a Jinja2 template or returns the relevant response.
6.  HTMX can request and update interactive page fragments.

### 6.2 Database change

1.  A schema change is made to the SQLAlchemy model definitions.
2.  An Alembic migration is generated and reviewed.
3.  The migration is applied to PostgreSQL.
4.  Tests verify the affected behavior.

### 6.3 Payment verification

1.  The application initiates the payment flow through the Razorpay
    integration.
2.  The browser may return payment-related information.
3.  The backend verifies the payment with the required trusted gateway
    information.
4.  The application records the verified result.
5.  A browser success message alone must never mark a payment as
    successful.

The exact Razorpay API operations and event-handling flow are
implementation details to be specified when the payment module is built.

### 6.4 Background job

1.  Application logic submits a background task to Celery.
2.  Redis acts as the message broker.
3.  A Celery worker executes the task.
4.  Renewal automation uses this processing foundation.

Detailed scheduling, retry and failure behavior remain open.

## 7. Deployment and testing

-   Docker is the deployment technology.
-   PostgreSQL and Redis are supporting infrastructure components.
-   Celery workers execute background jobs.
-   Pytest is used to test application behavior, authentication,
    permissions and module functionality.

The exact production topology, hosting provider, CI/CD process and
environment strategy have not been specified.

## 8. Implementation sequence

Follow the agreed sequence:

1.  Foundation and project setup
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

## 9. Architecture constraints

-   Do not add a separate React application.
-   Do not replace the selected database, ORM, migration tool or
    authentication approach without an explicit architecture decision.
-   Keep payment verification on the backend.
-   Keep Razorpay integration behind the gateway boundary.
-   Use Celery and Redis for the agreed background-job foundation.
-   Do not add services, technologies or modules that are outside the
    agreed scope.
