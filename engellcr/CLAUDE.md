# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django 5 SaaS app: **Cotización Express**, a Spanish-language product (deployed at engellcr.com) that lets small businesses in Costa Rica/LatAm register, build a branded business profile, manage clients and products, generate branded PDF quotations, share them by email/WhatsApp, and pay a monthly subscription. Domain language (models, URLs, templates, user-facing text) is Spanish — keep new code consistent with that.

This repository previously also contained a personal finance tracker (`finanzas_app`); it was deleted at the user's request and the domain now belongs entirely to `cotizador_app`.

## Commands

```bash
# Setup
python -m venv venv
venv\Scripts\activate              # Windows
pip install -r requirements.txt
cp .env.example .env               # then edit; for local SQLite use DATABASE_URL=sqlite:///db.sqlite3

# Database
python manage.py migrate      # data migration 0002_seed_roles_plans creates the 3 roles and 4 plans automatically

# Run
python manage.py runserver
```

To get a `staff/` panel admin locally: register normally at `/registro/`, verify the email, then assign the `admin` `Role` to that user via `/admin/` → `UserRole` (there is no CLI command for this).

```bash
# Tests — single file, cotizador_app/tests.py, 24 tests across 10 TestCase classes
python manage.py test cotizador_app
python manage.py test cotizador_app.tests.QuotaEnforcementTests            # one class
python manage.py test cotizador_app.tests.QuotaEnforcementTests.test_x    # one test
python manage.py test cotizador_app --keepdb                              # skip schema recreation on repeat runs
```

No lint/format tooling is configured. Beyond the automated tests, UI/flow changes are also verified by running the dev server and hitting routes directly.

Test gotchas:
- Rate-limiting (`@rate_limit`) is backed by Django's cache, which — unlike the DB — is **not** reset by `TestCase`'s transaction rollback between tests. The suite's shared base `TestCase` (top of `tests.py`) calls `cache.clear()` in `setUp()`; any new test class touching a rate-limited view must inherit from it, not `django.test.TestCase` directly.
- Django 5.0.6's template-instrumentation is incompatible with Python 3.14+ (`AttributeError: 'super' object has no attribute 'dicts'`) — run tests under Python 3.12, matching production.

**WeasyPrint** (used for PDF generation, see below) needs system libraries. The [Dockerfile](Dockerfile) installs them via apt for Railway/Linux deploys. On Windows, a native (non-MSYS/mingw) Python build is required for `pip install weasyprint`/`psycopg2-binary`/`Pillow` to find prebuilt wheels — an MSYS2 `mingw64` Python will fail to build these from source.

## Architecture

Single Django app, `cotizador_app/`, plus `config/` for settings/urls/wsgi. It's mounted at the URL root (`''`) in [config/urls.py](config/urls.py) — there is no other app competing for routes.

### Multi-tenancy: `Business` is the tenant root

Every tenant-scoped model (`Client`, `Product`, `Quotation`, `Payment`, etc.) carries a direct `business` FK to [`Business`](cotizador_app/models.py). **The data-isolation guarantee is one rule applied uniformly**: every queryset in a customer-facing view filters by `business=get_current_business(request)` (from [decorators.py](cotizador_app/decorators.py)), and every detail/edit/delete view does `get_object_or_404(Model, pk=pk, business=business)`. A user has at most one `Business` (`OneToOneField` on `owner`).

### Roles are explicit tables, not `is_staff`

`Role`/`UserRole` (a real many-to-many join, not a single field) drive authorization for the customer/admin/support role system — checked via `role_required(*codes)` in `decorators.py`, not Django's `is_staff`/permission system. The bespoke admin section (`staff/` routes, `views/staff.py`) is the delivered "admin panel," not just `/admin/` (Django admin is still registered for raw DB troubleshooting but isn't the product surface).

### Auth is fully self-contained — never relies on Django's global `LOGIN_URL`

`cotizador_login_required` (decorators.py) always passes `login_url='cotizador_app:login'` explicitly, and `business_required` additionally gates on `UserProfile.email_verified` (registration blocks real usage until the emailed verification link is clicked — a deliberate product choice, not a default). Registration (`views/auth.py:register`) creates `User` + `UserProfile` + `Business` + a trial `Subscription` + the first `UsageTracking` row in one `transaction.atomic()` block via `services.create_trial_business`.

### Usage/quota is a stored, race-safe counter — not computed live

`UsageTracking` holds a running `quotations_used` counter (spec explicitly wanted a real table here, not a computed `COUNT()`). `services.check_and_increment_usage(business)` does `select_for_update()` on the current usage row *inside the same transaction* as quotation creation — this is what makes "block creation after plan limit reached" concurrency-safe. A **new** `UsageTracking` row is created only when a new billing cycle starts (registration, or `services.activate_subscription()` after a verified payment) — never on a timer, since this stack has no scheduler/cron. Same pattern for `Subscription`: it's an FK (not OneToOne) on `Business`, so activating a new subscription creates a new row and plan history is preserved automatically.

### Payment abstraction: gateways vs. manual SINPE

`payments/base.py` defines a `PaymentProvider` interface (`create_pending_payment`, `get_redirect_url`, `verify_webhook`, `handle_webhook_event`) implemented by stub `TilopayProvider`/`PaypalProvider` classes (env-var driven, no invented API calls — real HTTP calls are marked `# TODO`). `PaymentEvent` has `unique_together(provider, external_event_id)`, which is the entire idempotency mechanism for webhook replay — a duplicate delivery raises `IntegrityError`, caught and treated as already-processed.

**SINPE Móvil is deliberately not a `PaymentProvider`** — it's manual (upload + admin review), so `payments/sinpe.py` exposes plain functions instead of forcing it into the redirect/webhook-shaped interface. All three payment paths (Tilopay, PayPal, SINPE) converge on the same `services.activate_subscription(payment)` — this is the one place "a subscription only activates after verified payment" is enforced, regardless of provider.

### PDF generation: content-hash reuse, not explicit cache invalidation

`pdf.py` computes a sha256 over everything a client would see (branding, client, items, terms, totals — **not** `status`) and compares it to the quotation's stored `pdf_content_hash`. Regeneration only happens on a mismatch. There is no separate "invalidate the PDF cache" step anywhere in the codebase — editing an item and saving naturally produces a new hash next time the PDF is requested. Uses WeasyPrint (`HTML(string=...).write_pdf()`), rendering the normal Django template `cotizacion_pdf.html`.

### Cache: must work with zero Redis configured

`CACHES` in settings.py switches between `RedisCache` (if `REDIS_URL` is set) and `LocMemCache` (default). Because `LocMemCache` can't scan/pattern-match keys, `cache.py`'s rule is: **cache keys are always deterministic/reconstructable from their inputs** — never rely on prefix invalidation. `ratelimit.py`'s `@rate_limit(scope, limit, window_seconds, key_kind='ip'|'user')` decorator is built directly on this cache module (no new dependency); note it's only approximate under `LocMemCache` with multiple gunicorn workers (per-worker memory) until `REDIS_URL` is set.

### File storage

Public files (quotation PDFs, business logos) use the default Cloudinary storage already configured for this project (`django-cloudinary-storage`). SINPE receipts are **private** — uploaded via the raw `cloudinary` SDK with `type='authenticated'` (not the default public storage class), and only ever served through an authenticated Django view that generates a short-lived signed URL — never a stored public URL.

### Help pages (`/panel/ayuda/` and `/staff/ayuda/`) must stay in sync with features

`ayuda.html` (customer-facing, `views/business.py:ayuda`) and `staff_ayuda.html` (admin-facing, `views/staff.py:staff_ayuda`) are plain static accordion pages, not DB-backed — content lives directly in the templates. **Whenever a customer-facing or admin-facing feature is added or changed, update the matching accordion section in these two templates in the same change**, so they never drift out of date.

### Production `DATABASE_URL` gotcha (real incident, watch for regressions)

`config/settings.py` does `dj_database_url.config(default=config('DATABASE_URL', default='sqlite:///db.sqlite3'))` — if Railway's web service is ever missing an env var named **exactly** `DATABASE_URL` (e.g. someone renames/replaces it with `DATABASE_PUBLIC_URL` or similar), the app silently falls back to an ephemeral SQLite file in the container with **no error**, and all data written in that state is lost on the next deploy. This already happened once in production. If anything looks like data is "disappearing" or a freshly-registered account can't be found, check the Railway web service's Variables tab for a variable literally named `DATABASE_URL` before assuming it's a code bug.

### Full implementation plan

See `C:\Users\enzapata\.claude\plans\warm-nibbling-journal.md` for the complete architecture/model/URL/phase breakdown this app was built from (models, payment abstraction, admin panel, security/cache/rate-limit design, phased build order, verification checklist).
