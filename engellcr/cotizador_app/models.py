import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


# ─── MONEDAS (Centro y Sudamérica + USD) ────────────────────────────────────
# Moneda "local" configurable por negocio (según su país) + USD siempre disponible.
# Compartido por Business.currency y Quotation.currency para no duplicar la lista.
CURRENCY_CHOICES = [
    ('CRC', 'Colones (₡) — Costa Rica'),
    ('NIO', 'Córdobas (C$) — Nicaragua'),
    ('GTQ', 'Quetzales (Q) — Guatemala'),
    ('HNL', 'Lempiras (L) — Honduras'),
    ('PAB', 'Balboas (B/.) — Panamá'),
    ('COP', 'Pesos colombianos ($) — Colombia'),
    ('PEN', 'Soles (S/) — Perú'),
    ('CLP', 'Pesos chilenos ($) — Chile'),
    ('ARS', 'Pesos argentinos ($) — Argentina'),
    ('BOB', 'Bolivianos (Bs) — Bolivia'),
    ('PYG', 'Guaraníes (₲) — Paraguay'),
    ('UYU', 'Pesos uruguayos ($U) — Uruguay'),
    ('VES', 'Bolívares (Bs) — Venezuela'),
    ('USD', 'Dólares ($)'),
]
CURRENCY_SYMBOLS = {
    'CRC': '₡', 'NIO': 'C$', 'GTQ': 'Q', 'HNL': 'L', 'PAB': 'B/.',
    'COP': '$', 'PEN': 'S/', 'CLP': '$', 'ARS': '$', 'BOB': 'Bs',
    'PYG': '₲', 'UYU': '$U', 'VES': 'Bs', 'USD': '$',
}


# ─── ROLES ─────────────────────────────────────────────────────────────────

class Role(models.Model):
    CUSTOMER = 'customer'
    ADMIN = 'admin'
    SUPPORT = 'support'
    CODE_CHOICES = [
        (CUSTOMER, 'Cliente'),
        (ADMIN, 'Administrador'),
        (SUPPORT, 'Soporte'),
    ]

    code = models.CharField(max_length=20, unique=True, choices=CODE_CHOICES)
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.name


class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cotizador_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_roles')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'role')]
        verbose_name = 'Rol de Usuario'
        verbose_name_plural = 'Roles de Usuario'

    def __str__(self):
        return f'{self.user} → {self.role}'


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cotizador_profile')
    phone = models.CharField(max_length=20, blank=True)
    email_verified = models.BooleanField(default=False)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f'Perfil de {self.user}'


# ─── NEGOCIO ───────────────────────────────────────────────────────────────

class Business(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='business')
    name = models.CharField('Nombre del negocio', max_length=150)
    legal_id = models.CharField('Cédula jurídica / ID fiscal', max_length=30, blank=True)
    email = models.EmailField('Correo de contacto', blank=True)
    phone = models.CharField('Teléfono', max_length=20, blank=True)
    address = models.TextField('Dirección', blank=True)
    logo = models.ImageField('Logo', upload_to='cotizador/logos/', blank=True, null=True)
    color_primary = models.CharField('Color principal', max_length=7, default='#1a3a5c')
    currency = models.CharField('Moneda', max_length=3, choices=CURRENCY_CHOICES, default='CRC')
    footer_note = models.TextField('Nota de pie de página', blank=True)
    sinpe_number = models.CharField('Número SINPE Móvil', max_length=20, blank=True)
    sinpe_account_holder = models.CharField('Titular de la cuenta SINPE', max_length=150, blank=True)
    next_quote_number = models.PositiveIntegerField(default=1)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Negocio'
        verbose_name_plural = 'Negocios'

    def __str__(self):
        return self.name

    @property
    def current_subscription(self):
        return self.subscriptions.order_by('-created_at').first()

    @property
    def current_usage(self):
        return self.usage_records.order_by('-created_at').first()


class BusinessNote(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nota Interna'
        verbose_name_plural = 'Notas Internas'

    def __str__(self):
        return f'Nota sobre {self.business} ({self.created_at:%Y-%m-%d})'


# ─── CLIENTES Y PRODUCTOS ────────────────────────────────────────────────

class Client(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField('Nombre completo', max_length=150)
    company_name = models.CharField('Empresa', max_length=150, blank=True)
    email = models.EmailField('Correo', blank=True)
    phone = models.CharField('Teléfono', max_length=20, blank=True)
    identification = models.CharField('Identificación', max_length=30, blank=True)
    address = models.TextField('Dirección', blank=True)
    notes = models.TextField('Notas', blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['business', 'name'])]
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return self.name


class Product(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    name = models.CharField('Nombre', max_length=150)
    description = models.TextField('Descripción', blank=True)
    sku = models.CharField('SKU', max_length=50, blank=True)
    unit_price = models.DecimalField('Precio unitario', max_digits=12, decimal_places=2)
    tax_pct = models.DecimalField('Impuesto (%)', max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['business', 'name'])]
        verbose_name = 'Producto/Servicio'
        verbose_name_plural = 'Productos/Servicios'

    def __str__(self):
        return self.name


# ─── COTIZACIONES ──────────────────────────────────────────────────────────

class Quotation(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_SENT = 'sent'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Borrador'),
        (STATUS_SENT, 'Enviada'),
        (STATUS_APPROVED, 'Aprobada'),
        (STATUS_REJECTED, 'Rechazada'),
        (STATUS_EXPIRED, 'Expirada'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='quotations')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='quotations')
    quote_number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    issue_date = models.DateField('Fecha')
    valid_until = models.DateField('Válida hasta')
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='CRC')
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField('Notas', blank=True)
    terms = models.TextField('Términos y condiciones', blank=True)
    pdf_file = models.FileField(upload_to='cotizador/pdfs/', blank=True, null=True)
    pdf_content_hash = models.CharField(max_length=64, blank=True)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('business', 'quote_number')]
        indexes = [
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['business', 'status']),
            models.Index(fields=['quote_number']),
        ]
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'

    def __str__(self):
        return f'{self.quote_number} — {self.client}'

    @property
    def simbolo(self):
        return CURRENCY_SYMBOLS.get(self.currency, self.currency)

    @property
    def is_editable(self):
        return self.status == self.STATUS_DRAFT


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Ítem de Cotización'
        verbose_name_plural = 'Ítems de Cotización'

    def __str__(self):
        return f'{self.description} x{self.quantity}'


class QuotationShareLink(models.Model):
    quotation = models.OneToOneField(Quotation, on_delete=models.CASCADE, related_name='share_link')
    token = models.CharField(max_length=43, unique=True, db_index=True)
    is_revoked = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Enlace Público de Cotización'
        verbose_name_plural = 'Enlaces Públicos de Cotización'

    def __str__(self):
        return f'Enlace {self.token[:8]}… → {self.quotation}'

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def rotate(self):
        self.token = secrets.token_urlsafe(32)
        self.is_revoked = False
        self.view_count = 0
        self.last_viewed_at = None
        self.approved_at = None
        self.rejected_at = None
        self.rejection_reason = ''
        self.save()

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at < timezone.now())

    @property
    def is_valid(self):
        return not self.is_revoked and not self.is_expired


# ─── PLANES Y SUSCRIPCIONES ─────────────────────────────────────────────────

class SubscriptionPlan(models.Model):
    FREE_TRIAL = 'free_trial'
    BASIC = 'basic'
    PRO = 'pro'
    BUSINESS = 'business'
    CODE_CHOICES = [
        (FREE_TRIAL, 'Prueba Gratis'),
        (BASIC, 'Básico'),
        (PRO, 'Pro'),
        (BUSINESS, 'Business'),
    ]

    code = models.CharField(max_length=20, unique=True, choices=CODE_CHOICES)
    name = models.CharField(max_length=50)
    price_crc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0,
        help_text='Precio en dólares — usado para cobros por PayPal (no soporta colones) y otros países fuera de Costa Rica')
    monthly_quote_limit = models.PositiveIntegerField(null=True, blank=True, help_text='Vacío = ilimitado')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['price_crc']
        verbose_name = 'Plan de Suscripción'
        verbose_name_plural = 'Planes de Suscripción'

    def __str__(self):
        return self.name


class Subscription(models.Model):
    TRIALING = 'trialing'
    ACTIVE = 'active'
    PAST_DUE = 'past_due'
    CANCELED = 'canceled'
    STATUS_CHOICES = [
        (TRIALING, 'Prueba'),
        (ACTIVE, 'Activa'),
        (PAST_DUE, 'Vencida'),
        (CANCELED, 'Cancelada'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=TRIALING)
    billing_cycle_start = models.DateTimeField(null=True, blank=True)
    billing_cycle_end = models.DateTimeField(null=True, blank=True)
    quota_override = models.PositiveIntegerField(null=True, blank=True, help_text='Anula el límite del plan si se define')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['business', 'status'])]
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f'{self.business} — {self.plan} ({self.get_status_display()})'

    @property
    def is_current(self):
        if self.status != self.ACTIVE:
            return False
        return bool(self.billing_cycle_end and self.billing_cycle_end >= timezone.now())

    @property
    def effective_limit(self):
        if self.quota_override is not None:
            return self.quota_override
        return self.plan.monthly_quote_limit


class UsageTracking(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='usage_records')
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, null=True, blank=True, related_name='usage_records')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField(null=True, blank=True, help_text='Vacío mientras está en prueba (conteo total, no mensual)')
    quotations_used = models.PositiveIntegerField(default=0)
    quota_limit = models.PositiveIntegerField(null=True, blank=True, help_text='Vacío = ilimitado')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['business', 'created_at'])]
        verbose_name = 'Registro de Uso'
        verbose_name_plural = 'Registros de Uso'

    def __str__(self):
        return f'{self.business} — {self.quotations_used}/{self.quota_limit or "∞"}'

    @property
    def is_blocked(self):
        return self.quota_limit is not None and self.quotations_used >= self.quota_limit


# ─── PAGOS ───────────────────────────────────────────────────────────────

class Payment(models.Model):
    TILOPAY = 'tilopay'
    PAYPAL = 'paypal'
    SINPE = 'sinpe'
    PROVIDER_CHOICES = [(TILOPAY, 'Tilopay'), (PAYPAL, 'PayPal'), (SINPE, 'SINPE Móvil')]

    PENDING = 'pending'
    PROCESSING = 'processing'
    APPROVED = 'approved'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'
    REFUNDED = 'refunded'
    EXPIRED = 'expired'
    STATUS_CHOICES = [
        (PENDING, 'Pendiente'),
        (PROCESSING, 'Procesando'),
        (APPROVED, 'Aprobado'),
        (FAILED, 'Fallido'),
        (CANCELLED, 'Cancelado'),
        (REJECTED, 'Rechazado'),
        (REFUNDED, 'Reembolsado'),
        (EXPIRED, 'Expirado'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='payments')
    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='CRC')
    external_reference = models.CharField(max_length=120, blank=True, help_text='ID de transacción del proveedor')
    internal_reference = models.CharField(max_length=40, unique=True, help_text='Referencia mostrada al cliente')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status']), models.Index(fields=['internal_reference'])]
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'

    def __str__(self):
        return f'{self.internal_reference} — {self.business} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.internal_reference:
            self.internal_reference = f'CX-{secrets.token_hex(4).upper()}'
        super().save(*args, **kwargs)


class PaymentEvent(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    provider = models.CharField(max_length=10, choices=Payment.PROVIDER_CHOICES)
    event_type = models.CharField(max_length=50)
    external_event_id = models.CharField(max_length=150)
    raw_payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
        unique_together = [('provider', 'external_event_id')]
        verbose_name = 'Evento de Pago'
        verbose_name_plural = 'Eventos de Pago'

    def __str__(self):
        return f'{self.provider}:{self.event_type} ({self.external_event_id})'


class SinpePaymentReceipt(models.Model):
    PENDING_REVIEW = 'pending_review'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    STATUS_CHOICES = [
        (PENDING_REVIEW, 'Pendiente de revisión'),
        (APPROVED, 'Aprobado'),
        (REJECTED, 'Rechazado'),
        (EXPIRED, 'Expirado'),
    ]

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='sinpe_receipt')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='sinpe_receipts')
    cloudinary_public_id = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=10, default='image')
    mime_type = models.CharField(max_length=50)
    file_size = models.PositiveIntegerField()
    reference_number = models.CharField('Referencia SINPE', max_length=50)
    payment_date = models.DateField('Fecha de pago')
    note = models.TextField('Nota', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING_REVIEW)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sinpe_reviews')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Comprobante SINPE'
        verbose_name_plural = 'Comprobantes SINPE'

    def __str__(self):
        return f'Comprobante {self.reference_number} — {self.business}'

    @property
    def is_expired(self):
        return self.status == self.PENDING_REVIEW and self.created_at < timezone.now() - timedelta(hours=72)

    @property
    def effective_status(self):
        if self.is_expired:
            return self.EXPIRED
        return self.status


# ─── AUDITORÍA Y CORREO ─────────────────────────────────────────────────────

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizador_audit_actions')
    business = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=60)
    target_repr = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'

    def __str__(self):
        return f'{self.action} — {self.actor} ({self.created_at:%Y-%m-%d %H:%M})'


class EmailLog(models.Model):
    SENT = 'sent'
    FAILED = 'failed'
    STATUS_CHOICES = [(SENT, 'Enviado'), (FAILED, 'Fallido')]

    business = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_logs')
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Registro de Correo'
        verbose_name_plural = 'Registros de Correo'

    def __str__(self):
        return f'{self.category} → {self.to_email} ({self.status})'
