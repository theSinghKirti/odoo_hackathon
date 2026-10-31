# Database Schema

## Subscription Manager

**Document status:** Logical schema baseline\
**Database:** PostgreSQL\
**ORM:** SQLAlchemy 2.0\
**Migrations:** Alembic

------------------------------------------------------------------------

## 1. Purpose

This document records the database entities implied by the agreed
Subscription Manager scope and the initial implementation context.

The project discussion confirms that the initial starter includes models
for users, roles and customers. The remaining business modules are in
the agreed application scope, but their detailed attributes and business
rules have not yet been specified.

To avoid inventing requirements, this document distinguishes confirmed
entities from entities that are required by the agreed modules but whose
exact schema is still to be designed.

## 2. Database conventions

-   PostgreSQL is the relational database.
-   SQLAlchemy 2.0 is used for ORM mapping.
-   Alembic is used to version and apply schema changes.
-   Schema changes must be represented by migrations.
-   Exact naming conventions, identifier types, timestamp policy and
    deletion policy are not yet established in the project discussion.
    They should be standardized during implementation rather than
    silently assumed here.

## 3. Confirmed initial entities

### 3.1 User

**Purpose:** Represents an account that can authenticate to the
application.

Confirmed by the initial implementation context: - A User model exists
in the starter. - Authentication uses JWT. - Passwords are hashed using
Argon2. - Password validation is part of the authentication
foundation. - Roles are part of the access-control foundation.

The exact User columns, lengths, uniqueness constraints and lifecycle
fields must be verified against the starter source code before changing
or documenting them as final.

### 3.2 Role

**Purpose:** Represents an application role used by the role-based
access foundation.

Confirmed roles: - Admin - Staff - Customer

The exact role storage strategy (for example, fixed values or database
records), permission representation and relationship cardinality must be
checked against the existing implementation before migration design is
finalized.

### 3.3 Customer

**Purpose:** Represents a customer account managed by the application.

A Customer model is included in the initial starter context. Customer
account management is also an agreed application module.

The exact Customer columns and its relationship to User must be verified
against the starter source code. Do not assume that every Customer must
have a login User unless that relationship is confirmed in the
implementation and requirements.

## 4. Business entities required by the agreed modules

The following entities are logical schema requirements implied by the
agreed modules. Their final columns, relationships and constraints
remain to be designed when each module is implemented.

  -----------------------------------------------------------------------
  Entity                  Purpose                 Status
  ----------------------- ----------------------- -----------------------
  Product                 Stores products managed Required by agreed
                          by the application      scope; fields TBD

  SubscriptionPlan        Stores subscription     Required by agreed
                          plans and their         scope; fields TBD
                          configuration           

  Quotation               Represents a quotation  Required by agreed
                                                  scope; workflow and
                                                  fields TBD

  Subscription            Represents a customer   Required by agreed
                          subscription            scope; lifecycle and
                                                  fields TBD

  Tax                     Represents tax          Required by agreed
                          configuration used by   scope; calculation
                          the application         rules and fields TBD

  Discount                Represents discount     Required by agreed
                          configuration           scope; eligibility and
                                                  fields TBD

  Invoice                 Represents              Required by agreed
                          automatically generated scope; numbering and
                          invoices                fields TBD

  Payment                 Represents payment      Required by agreed
                          records associated with scope; verification and
                          the Razorpay            status fields TBD
                          integration             
  -----------------------------------------------------------------------

These names describe logical entities, not a claim that corresponding
SQLAlchemy models already exist.

## 5. Relationships to establish during module implementation

The following relationships are suggested by the module
responsibilities, but exact cardinality and optionality must be
confirmed before migrations are written:

-   User and Role: required for role-based access. Whether a user can
    hold one or multiple roles is not specified.
-   Customer and User: the starter contains both concepts, but their
    exact relationship is not specified.
-   Customer and Subscription: subscriptions are managed for customers;
    exact cardinality is not specified.
-   Product and SubscriptionPlan: plans are part of the
    product/subscription domain; the exact relationship is not
    specified.
-   Quotation and Customer: quotation ownership/association must be
    defined.
-   Subscription and SubscriptionPlan: the plan associated with a
    subscription must be defined.
-   Invoice and Subscription: invoice association and invoice-generation
    rules must be defined.
-   Payment and Invoice or Subscription: the payment association must be
    defined as part of the payment workflow.
-   Tax and Discount associations: the entities or transaction records
    to which they apply must be defined.

No foreign-key layout should be treated as final until these rules are
agreed.

## 6. Security and data integrity

-   Passwords must be stored as Argon2 password hashes, never as
    plaintext.
-   Authentication is based on JWT as defined in the architecture.
-   Authorization must be enforced by the backend.
-   Payment status must be based on backend verification, not
    browser-provided success state.
-   Database constraints should enforce confirmed uniqueness and
    referential-integrity rules once those rules are specified.
-   Sensitive Razorpay credentials must not be stored as ordinary
    application business data. Their configuration mechanism belongs to
    application configuration and deployment setup.

## 7. Migration policy

-   SQLAlchemy model changes must be accompanied by Alembic migrations.
-   Migrations must be reviewed before application.
-   Existing data must be considered when changing or removing columns
    and relationships.
-   Tests must cover schema-dependent behavior.
-   Do not create speculative columns merely to anticipate unapproved
    features.

## 8. Schema decisions still required

The following are intentionally unresolved because they were not
established in the project discussion:

1.  Exact columns and constraints for User, Role and Customer.
2.  Whether permissions are represented as separate records, role
    mappings or another existing implementation.
3.  Whether one user can have multiple roles.
4.  The exact relationship between Customer and User.
5.  Product attributes and product lifecycle.
6.  Plan price representation, billing interval and plan configuration.
7.  Quotation fields, status values and conversion behavior.
8.  Subscription lifecycle fields and renewal-date rules.
9.  Tax calculation and jurisdiction fields.
10. Discount type, eligibility and stacking rules.
11. Invoice numbering, line-item structure and generation timing.
12. Payment status model, gateway identifiers, verification data and
    refund handling.
13. Timestamp, soft-delete and audit-field conventions.

These decisions should be made when the relevant module is designed.
Until then, this document is the logical schema baseline, not a
finalized physical SQL schema.

## 9. Implementation rule

Before modifying the database:

1.  Inspect the existing SQLAlchemy models.
2.  Preserve confirmed existing fields and relationships unless a
    deliberate change is approved.
3.  Agree on the module's missing business rules.
4.  Update the model definitions.
5.  Create and review the Alembic migration.
6.  Test the migration and affected application behavior.
