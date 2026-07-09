from django.db import transaction
from django.utils import timezone

from .models import (Business, Role, UserRole, Subscription, SubscriptionPlan,
                      UsageTracking, Quotation, AuditLog)


@transaction.atomic
def create_trial_business(user, business_name):
    """Called at registration: creates the Business, assigns the customer role,
    and starts a Free Trial subscription + usage record (3 quotations, lifetime, no card)."""
    role, _ = Role.objects.get_or_create(code=Role.CUSTOMER, defaults={'name': 'Cliente'})
    UserRole.objects.get_or_create(user=user, role=role)

    business = Business.objects.create(owner=user, name=business_name)

    plan = SubscriptionPlan.objects.get(code=SubscriptionPlan.FREE_TRIAL)
    subscription = Subscription.objects.create(
        business=business, plan=plan, status=Subscription.TRIALING,
    )
    UsageTracking.objects.create(
        business=business, subscription=subscription,
        period_start=timezone.now(), period_end=None,
        quotations_used=0, quota_limit=plan.monthly_quote_limit,
    )
    return business


def get_current_usage(business):
    usage = business.current_usage
    if usage is None:
        # Safety net: a business somehow without a usage row (shouldn't happen via create_trial_business).
        plan = business.current_subscription.plan if business.current_subscription else None
        usage = UsageTracking.objects.create(
            business=business, period_start=timezone.now(),
            quotations_used=Quotation.objects.filter(business=business).count(),
            quota_limit=plan.monthly_quote_limit if plan else None,
        )
    return usage


@transaction.atomic
def check_and_increment_usage(business):
    """Race-safe quota check + increment. Call inside the same transaction as quotation creation.
    Returns True if allowed (and increments), False if blocked (quota reached)."""
    usage = UsageTracking.objects.select_for_update().filter(business=business).order_by('-created_at').first()
    if usage is None:
        usage = get_current_usage(business)
    if usage.quota_limit is not None and usage.quotations_used >= usage.quota_limit:
        return False
    usage.quotations_used += 1
    usage.save(update_fields=['quotations_used', 'updated_at'])
    return True


def recalculate_totals(quotation):
    items = list(quotation.items.all())
    subtotal = sum((i.quantity * i.unit_price for i in items), start=0)
    discount_total = sum((i.quantity * i.unit_price * i.discount_pct / 100 for i in items), start=0)
    taxable = subtotal - discount_total
    tax_total = sum(
        ((i.quantity * i.unit_price - i.quantity * i.unit_price * i.discount_pct / 100) * i.tax_pct / 100
         for i in items), start=0)
    total = taxable + tax_total
    Quotation.objects.filter(pk=quotation.pk).update(
        subtotal=subtotal, discount_total=discount_total, tax_total=tax_total, total=total,
    )
    quotation.refresh_from_db(fields=['subtotal', 'discount_total', 'tax_total', 'total'])
    return quotation


@transaction.atomic
def next_quote_number(business_id):
    """Formats COT-YYYYMMDD-00001, with the 5-digit counter resetting to 1 each
    time the calendar date (at generation time) rolls over from the last one issued."""
    today = timezone.localdate()
    business = Business.objects.select_for_update().get(pk=business_id)
    if business.quote_number_reset_date != today:
        business.next_quote_number = 1
        business.quote_number_reset_date = today
    n = business.next_quote_number
    business.next_quote_number = n + 1
    business.save(update_fields=['next_quote_number', 'quote_number_reset_date'])
    return f'COT-{today:%Y%m%d}-{n:05d}'


@transaction.atomic
def activate_subscription(payment, actor=None):
    """Shared activation path for SINPE approval, and (eventually) verified Tilopay/PayPal webhooks.
    Creates a NEW Subscription + UsageTracking row (preserves history), marks payment approved."""
    business = payment.business
    plan = payment.plan
    now = timezone.now()
    cycle_end = now + timezone.timedelta(days=30)

    subscription = Subscription.objects.create(
        business=business, plan=plan, status=Subscription.ACTIVE,
        billing_cycle_start=now, billing_cycle_end=cycle_end,
    )
    UsageTracking.objects.create(
        business=business, subscription=subscription,
        period_start=now, period_end=cycle_end,
        quotations_used=0, quota_limit=plan.monthly_quote_limit,
    )
    payment.status = payment.APPROVED
    payment.completed_at = now
    payment.save(update_fields=['status', 'completed_at'])

    AuditLog.objects.create(
        actor=actor, business=business, action='subscription_activated',
        target_repr=str(subscription),
        metadata={'payment_id': payment.id, 'provider': payment.provider, 'plan': plan.code},
    )
    return subscription
