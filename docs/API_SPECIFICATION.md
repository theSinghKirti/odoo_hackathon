# API & Route Specification

## Subscription Manager (Multi-Tenant SaaS)

**Project:** Subscription Manager  
**Specification Version:** 2.0 (Fully Aligned)  
**Architecture:** FastAPI Modular Monolith (HTML/HTMX + JSON REST Endpoints)  
**Base REST Path:** `/api/v1`  
**Base Web/HTMX Paths:** `/admin`, `/staff`, `/portal`

---

## 1. Routing Strategy & Overview

Subscription Manager serves two types of consumers:
1. **Hypermedia Web Views (`/admin`, `/staff`, `/portal`):** Full pages and HTMX partials rendered via Jinja2 templates for Admin, Staff, and Customer users.
2. **REST API Endpoints (`/api/v1/...`):** Standard JSON endpoints for programmatic access, automated billing triggers, and Razorpay webhook ingestion.

---

## 2. Authentication & Account Security

Base Path: `/api/v1/auth`

### 2.1 Register User
- **Method:** `POST /api/v1/auth/register`
- **Request:**
  ```json
  {
    "organization_name": "Brightloop Software",
    "email": "admin@brightloop.com",
    "password": "SecurePassword123!",
    "full_name": "Sarah Connor"
  }
  ```
- **Validation Rules:**
  - Password must be $> 8$ characters, contain at least 1 uppercase, 1 lowercase, and 1 special character.
- **Response:** `201 Created`
  ```json
  {
    "id": "uuid",
    "email": "admin@brightloop.com",
    "role": "admin",
    "organization_id": "uuid"
  }
  ```

### 2.2 Login & Token Issue
- **Method:** `POST /api/v1/auth/login`
- **Request:**
  ```json
  {
    "email": "admin@brightloop.com",
    "password": "SecurePassword123!"
  }
  ```
- **Response:** `200 OK` (Sets HTTP-only `access_token` cookie)
  ```json
  {
    "status": "success",
    "role": "admin",
    "redirect_url": "/staff/dashboard"
  }
  ```

### 2.3 Password Reset Request
- **Method:** `POST /api/v1/auth/forgot-password`
- **Request:** `{"email": "customer@smallshop.com"}`
- **Response:** `200 OK` (`{"message": "If the account exists, a reset link has been dispatched."}`)

### 2.4 Complete Password Reset
- **Method:** `POST /api/v1/auth/reset-password`
- **Request:**
  ```json
  {
    "token": "secure_reset_token",
    "new_password": "NewStrongPassword456!"
  }
  ```
- **Response:** `200 OK`

---

## 3. Product Catalog, Variants & Add-ons

Base Path: `/api/v1/org/{org_id}/products`

### 3.1 List Products
- **Method:** `GET /api/v1/org/{org_id}/products?product_type=software`
- **Response:** `200 OK` (Collection of products with nested variants)

### 3.2 Create Product
- **Method:** `POST /api/v1/org/{org_id}/products`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "name": "Brightloop CRM",
    "product_type": "software",
    "sales_price": 1000.00,
    "cost_price": 400.00,
    "notes": "Core cloud subscription product"
  }
  ```
- **Response:** `201 Created`

### 3.3 Add Product Variant (Price Surcharge)
- **Method:** `POST /api/v1/org/{org_id}/products/{product_id}/variants`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "attribute_name": "Brand",
    "attribute_value": "Odoo",
    "price_extra": 560.00,
    "sku": "BL-CRM-ODOO"
  }
  ```
- **Response:** `201 Created`

---

## 4. Subscription Plans

Base Path: `/api/v1/org/{org_id}/plans`

### 4.1 Create Plan
- **Method:** `POST /api/v1/org/{org_id}/plans`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "name": "Enterprise Annual",
    "description": "Billed yearly with auto-close",
    "billing_interval": "yearly",
    "interval_count": 1,
    "base_price": 12000.00,
    "currency": "INR",
    "min_quantity": 5,
    "available_from": "2026-01-01",
    "available_until": "2026-12-31",
    "auto_close_on_expiry": true,
    "allow_early_close": true,
    "allow_pause": false,
    "allow_renewal": true
  }
  ```
- **Response:** `201 Created`

---

## 5. Tax & Discount Rules

### 5.1 Create Tax Rule
- **Method:** `POST /api/v1/org/{org_id}/tax-rules`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "name": "GST 18%",
    "rate": 18.00
  }
  ```
- **Response:** `201 Created`

### 5.2 Create Discount Rule
- **Method:** `POST /api/v1/org/{org_id}/discount-rules`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "name": "Bulk Seats 15% Off",
    "discount_type": "percentage",
    "discount_value": 15.00,
    "min_quantity": 10,
    "start_date": "2026-10-01",
    "end_date": "2026-12-31",
    "max_uses": 100,
    "scope": "subscription"
  }
  ```
- **Response:** `201 Created`

---

## 6. Quotation Templates & Quotation Operations

### 6.1 Create Quotation Template
- **Method:** `POST /api/v1/org/{org_id}/quotation-templates`
- **Permission:** Admin
- **Request:**
  ```json
  {
    "name": "Standard Enterprise Offer",
    "validity_days": 30,
    "plan_id": "plan_uuid",
    "lines": [
      {
        "product_id": "product_uuid",
        "variant_id": "variant_uuid",
        "quantity": 10,
        "unit_price": 1560.00
      }
    ]
  }
  ```
- **Response:** `201 Created`

### 6.2 Create Quotation from Template
- **Method:** `POST /api/v1/org/{org_id}/quotations`
- **Permission:** Admin, Staff
- **Request:**
  ```json
  {
    "template_id": "template_uuid",
    "customer_id": "customer_uuid",
    "start_date": "2026-11-01",
    "payment_terms": "Net 30"
  }
  ```
- **Response:** `201 Created` (Generates `QUO-2026-0001` with computed lines and expiry date)

### 6.3 Convert Quotation to Subscription
- **Method:** `POST /api/v1/org/{org_id}/quotations/{quotation_id}/convert`
- **Permission:** Admin, Staff
- **Response:** `200 OK`
  ```json
  {
    "message": "Quotation successfully converted to Subscription",
    "subscription_id": "sub_uuid",
    "subscription_number": "SUB-2026-0001",
    "status": "active"
  }
  ```

---

## 7. Subscriptions Lifecycle Operations

Base Path: `/api/v1/org/{org_id}/subscriptions`

### 7.1 List Subscriptions (Filtered for Finance Lead / Staff)
- **Method:** `GET /api/v1/org/{org_id}/subscriptions?status=active&page=1&limit=25`
- **Performance:** Optimized query with covering indexes executing in $< 50\text{ ms}$.

### 7.2 Pause Subscription
- **Method:** `POST /api/v1/org/{org_id}/subscriptions/{id}/pause`
- **Permission:** Admin, Staff (or Customer if `allow_pause = true`)
- **Response:** `200 OK` (`status = 'paused'`)

### 7.3 Resume Subscription
- **Method:** `POST /api/v1/org/{org_id}/subscriptions/{id}/resume`
- **Response:** `200 OK` (`status = 'active'`, `next_billing_date` recalculated)

### 7.4 Close Subscription
- **Method:** `POST /api/v1/org/{org_id}/subscriptions/{id}/close`
- **Response:** `200 OK` (`status = 'closed'`)

---

## 8. Billing Day & Invoicing

Base Path: `/api/v1/org/{org_id}/invoices`

### 8.1 Execute Billing Sweep (Worker or Manual Trigger)
- **Method:** `POST /api/v1/org/{org_id}/invoices/trigger-billing-run`
- **Permission:** Admin
- **Behavior:** Queries all due active subscriptions, creates Draft invoices, advances billing dates.
- **Response:** `200 OK` (`{"invoices_created": 42}`)

### 8.2 Confirm Invoice
- **Method:** `POST /api/v1/org/{org_id}/invoices/{id}/confirm`
- **Permission:** Admin, Staff
- **Response:** `200 OK` (`status = 'confirmed'`)

### 8.3 Download Invoice PDF
- **Method:** `GET /api/v1/org/{org_id}/invoices/{id}/pdf`
- **Response:** `200 OK` (`Content-Type: application/pdf`)

---

## 9. Payments: Offline Multi-Method & Razorpay

### 9.1 Record Offline Payment
- **Method:** `POST /api/v1/org/{org_id}/invoices/{invoice_id}/payments`
- **Permission:** Admin, Staff
- **Request:**
  ```json
  {
    "payment_method": "bank_transfer",
    "amount": 18408.00,
    "payment_date": "2026-11-02",
    "note": "NEFT ref UTR983210492 against Brightloop Invoice"
  }
  ```
- **Response:** `201 Created` (Updates invoice `amount_due` and marks `Paid` if settled)

### 9.2 Initiate Online Razorpay Payment (Customer Portal)
- **Method:** `POST /api/v1/portal/invoices/{invoice_id}/razorpay/order`
- **Permission:** Customer
- **Response:** `200 OK`
  ```json
  {
    "order_id": "order_EKf345G22",
    "amount": 1840800,
    "currency": "INR",
    "key_id": "rzp_test_public_key"
  }
  ```

### 9.3 Verify Razorpay Payment
- **Method:** `POST /api/v1/portal/invoices/{invoice_id}/razorpay/verify`
- **Permission:** Customer
- **Request:**
  ```json
  {
    "razorpay_order_id": "order_EKf345G22",
    "razorpay_payment_id": "pay_293847293",
    "razorpay_signature": "9a8b7c6d5e4f..."
  }
  ```
- **Response:** `200 OK` (Signature verified on server; invoice updated to `Paid`)

---

## 10. Customer Portal Views & Routes

Base Path: `/portal` (Served via Jinja2 + HTMX)

| Route | Method | Description |
| :--- | :--- | :--- |
| `/portal/dashboard` | `GET` | Customer overview of active subscriptions and recent invoices |
| `/portal/subscriptions` | `GET` | List of customer's subscriptions with line details |
| `/portal/subscriptions/{id}/pause` | `POST` | Self-service pause (HTMX inline toggle) |
| `/portal/subscriptions/{id}/renew` | `POST` | Self-service renewal request |
| `/portal/invoices` | `GET` | Customer's invoice history with status filters |
| `/portal/invoices/{id}/pay` | `GET` | Razorpay modal checkout trigger |

---

## 11. Finance Lead Summary & Analytics

Base Path: `/api/v1/org/{org_id}/analytics`

### 11.1 End-of-Month Executive Summary
- **Method:** `GET /api/v1/org/{org_id}/analytics/summary`
- **Permission:** Admin
- **Response:** `200 OK`
  ```json
  {
    "active_subscriptions": 1240,
    "monthly_recurring_revenue": 1450200.00,
    "annual_recurring_revenue": 17402400.00,
    "total_revenue_collected": 1280900.00,
    "overdue_invoices_count": 18,
    "overdue_invoices_amount": 169300.00
  }
  ```
- **Performance Guarantee:** Executes in under 2 seconds.

---

## 12. HTMX Hypermedia Partial Contracts (`app/web/`)

These routes represent the integration handshake between Developer 1 (Backend route logic) and Developer 2 (Frontend Jinja2 partials):

| Web Endpoint | Trigger Element | HTMX Attributes | Target ID | Swapped Partial / Content |
| :--- | :--- | :--- | :--- | :--- |
| `GET /web/products/search` | Search input | `hx-get="/web/products/search" hx-trigger="keyup changed delay:300ms"` | `#product-table-body` | Replaces `<tbody>` with filtered `partials/product_rows.html` |
| `POST /web/products` | Create product form | `hx-post="/web/products" hx-target="#product-table-body" hx-swap="afterbegin"` | `#product-table-body` | Prepend new product row and dispatches toast event |
| `POST /web/products/{id}/variants` | Add variant modal | `hx-post="..." hx-target="#variant-list"` | `#variant-list` | Appends new variant row with surcharge badge |
| `POST /web/quotes/{id}/convert` | "Convert to Sub" btn | `hx-post="..." hx-target="#quote-status-card" hx-swap="outerHTML"` | `#quote-status-card` | Swaps quote status card and reveals link to new subscription |
| `POST /web/subs/{id}/pause` | Pause button | `hx-post="..." hx-target="#sub-status-badge" hx-swap="outerHTML"` | `#sub-status-badge` | Returns `<span class="badge badge-paused">Paused</span>` |
| `POST /web/subs/{id}/resume` | Resume button | `hx-post="..." hx-target="#sub-status-badge" hx-swap="outerHTML"` | `#sub-status-badge` | Returns `<span class="badge badge-active">Active</span>` |
| `POST /web/invoices/{id}/confirm`| Confirm invoice btn | `hx-post="..." hx-target="#invoice-header-actions"` | `#invoice-header-actions`| Swaps action buttons (disables edit, enables print & pay) |
| `POST /web/invoices/{id}/payments`| Payment modal submit| `hx-post="..." hx-target="#invoice-payment-summary"`| `#invoice-payment-summary`| Swaps balance due, adds payment line, updates status badge |
| `GET /web/finance/summary` | Date range selector | `hx-get="..." hx-target="#finance-stat-cards" hx-swap="innerHTML"` | `#finance-stat-cards` | Fast swap of the 4 financial metric summary cards |