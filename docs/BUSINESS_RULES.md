# Business Rules Specification

## Subscription Manager (Multi-Tenant SaaS)

**Project:** Subscription Manager  
**Document Status:** Approved Business Rules & Domain Logic  
**Scope:** Authoritative business logic governing multi-tenancy, authentication, catalog, quoting, subscriptions, automated invoicing, taxes, discounts, multi-method payments, customer portal, and finance reporting.

---

## 1. System Invariants & Core Principles

1. **Tenant Isolation:** A tenant (organization) can never view, query, or mutate another organization's records under any circumstance.
2. **Deterministic Financial Math:** All monetary operations must use exact decimal arithmetic (`NUMERIC(12, 2)`). Floating-point arithmetic is prohibited.
3. **No Double Billing or Skipping:** The automated billing engine must ensure that no active subscription is billed twice in the same cycle or skipped.
4. **Authoritative Backend Verification:** No subscription or invoice can transition to `Active` or `Paid` based solely on a client-side frontend message. All payments require server-side signature validation or explicit staff ledger entry.
5. **Historical Immutability:** Invoices marked `Paid` and recorded payment records are immutable financial documents. Corrections must occur via credit adjustments or explicit cancellation.
6. **Sub-2-Second Performance:** Every page, filter, and analytical summary must respond in under two seconds under production load.

---

## 2. Multi-Tenancy & User Roles

### 2.1 Multi-Tenancy Rules
- Subscription Manager supports multiple isolated organizations (tenants).
- The default tenant implementation models **Brightloop Software**.
- Each organization owns its catalog, customers, plans, quotes, subscriptions, invoices, taxes, and discounts.

### 2.2 Roles & Permission Matrix

| Capability | Admin | Staff | Customer |
| :--- | :---: | :---: | :---: |
| Manage Staff Accounts | **Yes** (Admin-only) | No | No |
| Configure Products & Variants | **Yes** | No | No |
| Configure Plans & Lifecycle Policies | **Yes** | No | No |
| Configure Tax & Discount Rules | **Yes** | No | No |
| Create Quotation Templates | **Yes** | No | No |
| View Finance Lead Summary (MRR/ARR) | **Yes** | No | No |
| Create / Edit Quotations from Templates | **Yes** | **Yes** | No |
| Convert Quotation to Subscription | **Yes** | **Yes** | No |
| Manage Subscriptions (Pause/Resume/Close) | **Yes** | **Yes** | Conditional (if plan allows) |
| Confirm, Cancel, Send, Print Invoices | **Yes** | **Yes** | No (view/print only) |
| Record Offline Payments (Method, Date, Note) | **Yes** | **Yes** | No |
| Access Customer Self-Service Portal (`/portal`)| No | No | **Yes** (Own records only) |
| Pay Invoices Online via Razorpay | No | No | **Yes** |

### 2.3 Authentication & Password Requirements
- **Account Identification:** Email address is the unique identity within an organization.
- **Strict Password Policy:** Password length must be **greater than 8 characters** and contain:
  - At least 1 uppercase letter (`[A-Z]`)
  - At least 1 lowercase letter (`[a-z]`)
  - At least 1 special character (`[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]`)
- **Password Reset:** If forgotten, a secure reset token is generated and delivered to the registered email address with a 1-hour expiration window.
- **Session Security:** JWT access tokens are stored in secure, `HttpOnly`, `SameSite=Lax` cookies.

---

## 3. Product Catalog, Variants & Add-ons

### 3.1 Product Creation
- Admins create products with:
  - `name`: Human-readable label (e.g., "CRM Suite", "Storage Pack").
  - `product_type`: `software`, `service`, `addon`, or `physical`.
  - `sales_price`: Default unit selling price.
  - `cost_price`: Internal baseline cost.
  - `notes`: Operational or delivery instructions.

### 3.2 Product Variants & Surcharges
- Products can have variants configured by attribute dimension (e.g. `Brand`, `Tier`).
- Each variant value defines a `price_extra` surcharge added to the product's base `sales_price`.
  - *Example:* A software product base price is ₹1,000. Selecting the variant `Brand = Odoo` with `price_extra = 560.00` results in an effective unit sales price of **₹1,560.00**.

### 3.3 Add-on Products
- Products of type `addon` can be dynamically attached or detached from a subscription.
- Add-ons inherit the billing interval of the parent subscription.

---

## 4. Subscription Plans & Intervals

### 4.1 Plan Configuration
- Plans define recurring terms: Name, Description, Base Price, Currency, and Minimum Quantity.
- **Billing Intervals:** Supported intervals are:
  - `daily`: Bills every 1 day.
  - `weekly`: Bills every 7 days.
  - `monthly`: Bills every calendar month (handling month-end dates).
  - `yearly`: Bills every calendar year.
- **Availability Window:** Plans can have `available_from` and `available_until` dates. New quotes/subscriptions cannot be created for plans outside their active window.

### 4.2 Lifecycle Policy Flags
Admins configure lifecycle permissions per plan:
- `auto_close_on_expiry`: If `True`, the subscription automatically transitions to `Closed` upon reaching `expiry_date`.
- `allow_early_close`: If `True`, staff or customers can terminate the subscription prior to the scheduled end date.
- `allow_pause`: If `True`, the subscription can be temporarily paused and resumed.
- `allow_renewal`: If `True`, the subscription can be renewed for subsequent terms.

---

## 5. Quotation Templates & Quotation Workflow

### 5.1 Quotation Templates
- Created by Admins to standardize common sales packages.
- Defines: Template Name, Default Plan, pre-configured product lines (products, variants, quantities), and Validity Duration in days (e.g., 15 or 30 days).

### 5.2 Quotation Creation
- Sales reps start by selecting a template or creating a quote from scratch.
- The system automatically populates the plan, line items, and computes:
  $$\text{expiry\_date} = \text{start\_date} + \text{validity\_days}$$
- Quotation lines include: Product, Variant, Quantity, Unit Price, Applied Tax, Discount, and Net Line Total.

### 5.3 Quotation Conversion to Subscription
- A quotation begins in `Draft` and moves to `Quotation` when delivered to the customer.
- When the customer agrees, the quotation is marked `Confirmed`.
- Staff triggers **Convert to Subscription**:
  - Automatically creates a new `Subscription` record with a sequential number (e.g., `SUB-2026-0001`).
  - Deep-copies quotation lines into subscription lines.
  - Sets subscription `status = 'Active'` and calculates initial `next_billing_date`.

---

## 6. Subscription Engine & State Machine

### 6.1 State Transitions
$$\text{Draft} \longrightarrow \text{Quotation} \longrightarrow \text{Confirmed} \longrightarrow \text{Active} \longrightarrow \text{Closed}$$

- **`Draft`:** Internal proposal being authored.
- **`Quotation`:** Presented to customer; awaiting acceptance.
- **`Confirmed`:** Offer accepted; ready for activation.
- **`Active`:** Operational; recurring invoices generate automatically.
- **`Paused`:** Operational hold; automated billing skips this subscription until resumed.
- **`Closed`:** Terminal state; reached upon expiry (if auto-close enabled), early termination, or non-renewal. Closed subscriptions cannot be reopened (a new quote/subscription is required).

### 6.2 Pause and Resume Logic
- Subscriptions with `allow_pause = True` can be paused by Staff or by the Customer in their portal.
- Pausing suspends entitlement and pauses billing day invoice generation.
- Resuming restores `Active` status and recalculates the `next_billing_date`.

---

## 7. Billing Day & Invoice Automation

### 7.1 Automated Billing Execution
- The billing worker runs daily at 00:00 UTC.
- Selects all subscriptions matching:
  $$\text{status} = \text{'Active'} \quad \text{AND} \quad \text{next\_billing\_date} \le \text{CURRENT\_DATE}$$
- **Concurrency & Idempotency Lock:**
  - Uses `SELECT ... FOR UPDATE SKIP LOCKED` inside a transaction.
  - Verifies that `last_billed_date < next_billing_date` before creating an invoice.
  - Generates the invoice and line items.
  - Advances `next_billing_date` according to the plan interval (`daily`, `weekly`, `monthly`, `yearly`).
  - Sets `last_billed_date = CURRENT_DATE`.
  - Commits the transaction, ensuring **no subscription is billed twice or skipped**.

### 7.2 Invoice Lifecycle & Actions
$$\text{Draft} \longrightarrow \text{Confirmed} \longrightarrow \text{Paid}$$

- Invoices generate in `Draft` state.
- **Staff Actions:**
  - **Confirm:** Finalizes the invoice into `Confirmed` state and locks line items from edits.
  - **Cancel:** Voids an unpaid invoice (`Cancelled`).
  - **Send:** Dispatches PDF invoice and payment link via email.
  - **Print:** Generates a downloadable, clean HTML/PDF invoice.

---

## 8. Tax Rules Engine

- Admins configure tax rules (e.g., `GST 18%`, `VAT 20%`).
- Taxes are calculated automatically at the line-item level:
  $$\text{line\_tax} = (\text{unit\_price} \times \text{quantity} - \text{discount}) \times \frac{\text{tax\_rate}}{100}$$
- Total tax on an invoice is the deterministic sum of all line item taxes.

---

## 9. Discount Rules Engine

### 9.1 Discount Rule Criteria
Admins configure rules with:
- **Type:** `fixed_amount` (e.g. ₹500 off) or `percentage` (e.g. 10% off).
- **Triggers:** `min_purchase_amount` (e.g. order value $\ge$ ₹10,000) or `min_quantity` (e.g. quantity $\ge 10$ seats).
- **Date Range:** `start_date` and `end_date`.
- **Usage Ceiling:** `max_uses` (e.g., first 50 customers).
- **Scope:**
  - `product`: Applies exclusively to the specified product line item.
  - `subscription`: Applies across the overall subscription subtotal.

### 9.2 Automated Invoice Application & Depletion
- During invoice generation, the billing engine checks all active discount rules.
- If qualifying conditions are met, the discount is automatically applied to the invoice.
- The rule's `times_used` counter is atomically incremented.
- Once `times_used >= max_uses` or `CURRENT_DATE > end_date`, the rule ceases to apply on subsequent invoices without manual intervention.

---

## 10. Payment Processing (Multi-Method Offline + Razorpay)

### 10.1 Multi-Method Offline Recording
- Brightloop receives payments via bank transfers, cheques, and cash on various days.
- Staff records each payment against the invoice:
  - `payment_method`: `bank_transfer`, `cheque`, `cash`, `other`.
  - `amount`: Monetary value received.
  - `payment_date`: Date the funds were realized.
  - `note`: Reference (e.g., UTR / cheque number).
- Multiple partial payments can be recorded against a single invoice.

### 10.2 Online Razorpay Integration
- Customers in the portal can click "Pay Online" for any `Confirmed` invoice with an outstanding balance.
- Backend creates a Razorpay Order (`razorpay_order_id`).
- Upon client checkout completion, the backend verifies the cryptographic signature:
  $$\text{HMAC-SHA256}(\text{order\_id} + "|" + \text{payment\_id}, \text{key\_secret}) \equiv \text{signature}$$
- If valid, a `Payment` record is created, and the invoice balance is updated.

### 10.3 Automatic Settlement
- Every payment updates the invoice:
  $$\text{amount\_paid} = \sum \text{payments.amount}$$
  $$\text{amount\_due} = \text{total\_amount} - \text{amount\_paid}$$
- When $\text{amount\_due} \le 0$, the invoice status transitions automatically to **`Paid`**.

---

## 11. Customer Self-Service Portal

- Customers log in at `/portal` using their credentials.
- **Strict Data Isolation:** Customers can query and view only records matching their `customer_id`.
- **Self-Service Capabilities:**
  - View list of subscriptions with line items, next renewal dates, and status.
  - Pause, resume, or cancel subscriptions (subject to plan `allow_pause` and `allow_early_close` rules).
  - View invoices, download PDF copies, and pay outstanding balances online.

---

## 12. Finance Lead Reporting & Analytics

- Executive summary view for Admins and Finance Leads:
  - **Active Subscriptions:** Real-time count of active subscription agreements.
  - **Monthly Recurring Revenue (MRR):** Normalized monthly subscription value:
    $$\text{MRR} = \sum_{\text{daily}} (\text{val} \times 30) + \sum_{\text{weekly}} (\text{val} \times 4.33) + \sum_{\text{monthly}} \text{val} + \sum_{\text{yearly}} \left(\frac{\text{val}}{12}\right)$$
  - **Annual Recurring Revenue (ARR):** $\text{MRR} \times 12$.
  - **Payments Collected:** Total funds realized in selected period.
  - **Outstanding & Overdue Invoices:** Amount owed with filterable chase list sorted by oldest overdue invoices.
- **Performance Guarantee:** All analytical queries must leverage covering database indexes to render within **under 2 seconds**.