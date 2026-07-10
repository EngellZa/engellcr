from django.contrib import admin

from .models import (Role, UserRole, UserProfile, Business, BankAccount, BusinessNote, Client,
                      Product, Quotation, QuotationItem, QuotationShareLink, SubscriptionPlan,
                      Subscription, UsageTracking, Payment, PaymentEvent, SinpePaymentReceipt,
                      AuditLog, EmailLog)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'assigned_at']
    list_filter = ['role']
    search_fields = ['user__email', 'user__username']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_verified', 'phone']
    list_filter = ['email_verified']
    search_fields = ['user__email']


class BusinessNoteInline(admin.TabularInline):
    model = BusinessNote
    extra = 0
    readonly_fields = ['author', 'created_at']


class BankAccountInline(admin.TabularInline):
    model = BankAccount
    extra = 0


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'email', 'currency', 'is_deleted', 'created_at']
    search_fields = ['name', 'owner__email', 'legal_id']
    inlines = [BankAccountInline, BusinessNoteInline]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'business', 'email', 'phone', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'company_name', 'business__name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'business', 'unit_price', 'tax_pct', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'sku', 'business__name']


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quote_number', 'business', 'client', 'status', 'total', 'issue_date']
    list_filter = ['status', 'currency']
    search_fields = ['quote_number', 'business__name', 'client__name']
    date_hierarchy = 'issue_date'
    inlines = [QuotationItemInline]


@admin.register(QuotationShareLink)
class QuotationShareLinkAdmin(admin.ModelAdmin):
    list_display = ['quotation', 'token', 'is_revoked', 'view_count', 'expires_at']
    search_fields = ['token', 'quotation__quote_number']


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'price_crc', 'price_usd', 'monthly_quote_limit', 'is_active']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .cache import cx_delete, plan_list_key
        cx_delete(plan_list_key())


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['business', 'plan', 'status', 'billing_cycle_start', 'billing_cycle_end', 'quota_override']
    list_filter = ['status', 'plan']
    search_fields = ['business__name']


@admin.register(UsageTracking)
class UsageTrackingAdmin(admin.ModelAdmin):
    list_display = ['business', 'quotations_used', 'quota_limit', 'period_start', 'period_end']
    search_fields = ['business__name']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['internal_reference', 'business', 'provider', 'status', 'amount', 'currency', 'created_at']
    list_filter = ['provider', 'status']
    search_fields = ['business__name', 'external_reference', 'internal_reference']
    date_hierarchy = 'created_at'


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ['provider', 'event_type', 'external_event_id', 'processed', 'received_at']
    list_filter = ['provider', 'processed']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SinpePaymentReceipt)
class SinpePaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ['reference_number', 'business', 'status', 'payment_date', 'created_at']
    list_filter = ['status']
    search_fields = ['reference_number', 'business__name']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'actor', 'business', 'created_at']
    list_filter = ['action']
    search_fields = ['business__name', 'actor__email']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['category', 'to_email', 'status', 'created_at']
    list_filter = ['category', 'status']
    search_fields = ['to_email']

    def has_add_permission(self, request):
        return False
