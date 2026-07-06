"""Automated tests for the MVP flows called out explicitly in the product spec:
registration/trial, cross-tenant isolation, quota enforcement, quotation totals,
PDF generation, public share-link security, SINPE upload validation + approval,
staff-panel role gating, webhook idempotency, and the health endpoint."""
from datetime import date, timedelta
from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase as DjangoTestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone

from .emailing import make_verification_token
from .models import (Business, Client, Product, Quotation, QuotationShareLink,
                      SubscriptionPlan, Payment, PaymentEvent, SinpePaymentReceipt,
                      Role, UserRole, AuditLog)
from .payments.sinpe import approve_receipt, reject_receipt
from .services import check_and_increment_usage, recalculate_totals


class TestCase(DjangoTestCase):
    """Base TestCase that clears the cache before each test. Necessary because
    @rate_limit is backed by Django's cache, which — unlike the database — is NOT
    reset between tests by TestCase's transaction rollback. Without this, tests run
    later in the suite start hitting real rate limits (e.g. 5 registrations/hour)
    left over from earlier tests and fail with confusing "object does not exist" errors."""
    def setUp(self):
        super().setUp()
        cache.clear()


def _register_and_verify(client, email, business_name, password='ClaveSegura123!'):
    client.post(reverse('cotizador_app:register'), {
        'full_name': 'Test User', 'email': email, 'business_name': business_name,
        'password': password, 'confirm_password': password,
    })
    user = User.objects.get(email=email)
    client.get(reverse('cotizador_app:verificar_correo', args=[make_verification_token(user.id)]))
    return user, Business.objects.get(owner=user)


class RegistrationTests(TestCase):
    def test_registration_creates_trial_subscription_and_usage(self):
        client = TestClient()
        user, business = _register_and_verify(client, 'trial@example.com', 'Trial Biz')
        sub = business.current_subscription
        usage = business.current_usage
        self.assertEqual(sub.status, 'trialing')
        self.assertEqual(sub.plan.code, 'free_trial')
        self.assertEqual(usage.quota_limit, 3)
        self.assertEqual(usage.quotations_used, 0)


class TenantIsolationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_a = TestClient()
        self.user_a, self.business_a = _register_and_verify(self.client_a, 'owner_a@example.com', 'Negocio A')
        self.client_b = TestClient()
        self.user_b, self.business_b = _register_and_verify(self.client_b, 'owner_b@example.com', 'Negocio B')

        self.customer = Client.objects.create(business=self.business_a, name='Cliente A')
        self.quotation = Quotation.objects.create(
            business=self.business_a, client=self.customer, quote_number='COT-0001',
            issue_date=date.today(), valid_until=date.today() + timedelta(days=15),
        )

    def test_other_business_cannot_view_quotation(self):
        resp = self.client_b.get(reverse('cotizador_app:cotizacion_detalle', args=[self.quotation.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_other_business_cannot_edit_quotation(self):
        resp = self.client_b.get(reverse('cotizador_app:cotizacion_editar', args=[self.quotation.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_client_list_scoped_to_own_business(self):
        Client.objects.create(business=self.business_b, name='Cliente B')
        resp = self.client_a.get(reverse('cotizador_app:cliente_lista'))
        self.assertContains(resp, 'Cliente A')
        self.assertNotContains(resp, 'Cliente B')


class QuotaEnforcementTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_t = TestClient()
        self.user, self.business = _register_and_verify(self.client_t, 'quota@example.com', 'Quota Biz')
        self.customer = Client.objects.create(business=self.business, name='Cliente')

    def test_blocks_after_trial_limit_reached(self):
        for _ in range(3):
            allowed = check_and_increment_usage(self.business)
            self.assertTrue(allowed)
        blocked = check_and_increment_usage(self.business)
        self.assertFalse(blocked)

    def test_quotation_create_view_blocked_at_limit(self):
        for _ in range(3):
            check_and_increment_usage(self.business)
        resp = self.client_t.get(reverse('cotizador_app:cotizacion_crear'))
        self.assertRedirects(resp, reverse('cotizador_app:plan_actual'))


class QuotationTotalsTests(TestCase):
    def test_totals_computed_from_items(self):
        client_t = TestClient()
        user, business = _register_and_verify(client_t, 'totals@example.com', 'Totals Biz')
        customer = Client.objects.create(business=business, name='Cliente')
        quotation = Quotation.objects.create(
            business=business, client=customer, quote_number='COT-0001',
            issue_date=date.today(), valid_until=date.today() + timedelta(days=15),
        )
        quotation.items.create(description='Item 1', quantity=1, unit_price=50000, discount_pct=0, tax_pct=13)
        quotation.items.create(description='Item 2', quantity=2, unit_price=20000, discount_pct=10, tax_pct=13)
        recalculate_totals(quotation)
        self.assertEqual(quotation.subtotal, 90000)
        self.assertEqual(quotation.discount_total, 4000)
        self.assertEqual(quotation.tax_total, 11180)
        self.assertEqual(quotation.total, 97180)


class PdfGenerationTests(TestCase):
    def test_pdf_generated_and_reused_until_content_changes(self):
        client_t = TestClient()
        user, business = _register_and_verify(client_t, 'pdf@example.com', 'PDF Biz')
        customer = Client.objects.create(business=business, name='Cliente')
        quotation = Quotation.objects.create(
            business=business, client=customer, quote_number='COT-0001',
            issue_date=date.today(), valid_until=date.today() + timedelta(days=15),
        )
        quotation.items.create(description='Item', quantity=1, unit_price=1000, tax_pct=0)
        recalculate_totals(quotation)

        resp = client_t.get(reverse('cotizador_app:cotizacion_pdf', args=[quotation.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        quotation.refresh_from_db()
        first_hash, first_ts = quotation.pdf_content_hash, quotation.pdf_generated_at
        self.assertTrue(first_hash)

        client_t.get(reverse('cotizador_app:cotizacion_pdf', args=[quotation.pk]))
        quotation.refresh_from_db()
        self.assertEqual(quotation.pdf_content_hash, first_hash)
        self.assertEqual(quotation.pdf_generated_at, first_ts)


class PublicShareLinkTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_t = TestClient()
        self.user, self.business = _register_and_verify(self.client_t, 'share@example.com', 'Share Biz')
        self.customer = Client.objects.create(business=self.business, name='Cliente', email='c@example.com')
        self.quotation = Quotation.objects.create(
            business=self.business, client=self.customer, quote_number='COT-0001', status='sent',
            issue_date=date.today(), valid_until=date.today() + timedelta(days=15),
        )
        self.link = QuotationShareLink.objects.create(quotation=self.quotation)

    def test_valid_token_accessible(self):
        resp = TestClient().get(reverse('public_quote_view', args=[self.link.token]))
        self.assertEqual(resp.status_code, 200)

    def test_revoked_token_returns_404(self):
        self.link.is_revoked = True
        self.link.save()
        resp = TestClient().get(reverse('public_quote_view', args=[self.link.token]))
        self.assertEqual(resp.status_code, 404)

    def test_expired_token_returns_404(self):
        self.link.expires_at = timezone.now() - timedelta(days=1)
        self.link.save()
        resp = TestClient().get(reverse('public_quote_view', args=[self.link.token]))
        self.assertEqual(resp.status_code, 404)

    def test_token_is_long_random_and_unique(self):
        other_link = QuotationShareLink.objects.create(
            quotation=Quotation.objects.create(
                business=self.business, client=self.customer, quote_number='COT-0002',
                issue_date=date.today(), valid_until=date.today() + timedelta(days=15),
            )
        )
        self.assertGreaterEqual(len(self.link.token), 32)
        self.assertNotEqual(self.link.token, other_link.token)

    def test_approve_updates_status(self):
        resp = TestClient().post(reverse('public_quote_approve', args=[self.link.token]))
        self.assertEqual(resp.status_code, 302)
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, 'approved')


def _make_valid_png():
    buf = BytesIO()
    Image.new('RGB', (10, 10), color='white').save(buf, format='PNG')
    return SimpleUploadedFile('comprobante.png', buf.getvalue(), content_type='image/png')


class SinpePaymentTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_t = TestClient()
        self.user, self.business = _register_and_verify(self.client_t, 'sinpe@example.com', 'Sinpe Biz')
        self.plan = SubscriptionPlan.objects.get(code='basic')
        self.payment = Payment.objects.create(business=self.business, plan=self.plan, provider=Payment.SINPE, amount=5000, currency='CRC')

        admin_role, _ = Role.objects.get_or_create(code=Role.ADMIN, defaults={'name': 'Administrador'})
        self.staff_user = User.objects.create_user(username='sinpe_admin@example.com', email='sinpe_admin@example.com', password='ClaveSegura123!')
        UserRole.objects.create(user=self.staff_user, role=admin_role)

    def test_oversized_file_rejected(self):
        big_file = SimpleUploadedFile('big.png', b'0' * (6 * 1024 * 1024), content_type='image/png')
        resp = self.client_t.post(
            reverse('cotizador_app:sinpe_subir_comprobante', args=[self.payment.id]),
            {'comprobante': big_file, 'reference_number': 'REF1', 'payment_date': '2026-07-01', 'note': ''},
        )
        self.assertEqual(resp.status_code, 200)  # redisplays form with error, doesn't create a receipt
        self.assertFalse(SinpePaymentReceipt.objects.filter(payment=self.payment).exists())

    def test_wrong_file_type_rejected(self):
        exe_file = SimpleUploadedFile('evil.exe', b'MZ\x00\x00', content_type='application/octet-stream')
        resp = self.client_t.post(
            reverse('cotizador_app:sinpe_subir_comprobante', args=[self.payment.id]),
            {'comprobante': exe_file, 'reference_number': 'REF1', 'payment_date': '2026-07-01', 'note': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SinpePaymentReceipt.objects.filter(payment=self.payment).exists())

    def test_valid_receipt_upload_succeeds(self):
        resp = self.client_t.post(
            reverse('cotizador_app:sinpe_subir_comprobante', args=[self.payment.id]),
            {'comprobante': _make_valid_png(), 'reference_number': 'REF1', 'payment_date': '2026-07-01', 'note': ''},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SinpePaymentReceipt.objects.filter(payment=self.payment).exists())

    def test_admin_approval_activates_subscription(self):
        receipt = SinpePaymentReceipt.objects.create(
            payment=self.payment, business=self.business, cloudinary_public_id='fake',
            resource_type='image', mime_type='image/png', file_size=100,
            reference_number='REF1', payment_date=date.today(),
        )
        approve_receipt(receipt, self.staff_user)
        self.business.refresh_from_db()
        self.assertEqual(self.business.current_subscription.plan.code, 'basic')
        self.assertEqual(self.business.current_subscription.status, 'active')
        self.assertEqual(self.payment.pk and Payment.objects.get(pk=self.payment.pk).status, 'approved')
        self.assertTrue(AuditLog.objects.filter(action='sinpe_approved', business=self.business).exists())

    def test_rejection_requires_reason_and_records_it(self):
        receipt = SinpePaymentReceipt.objects.create(
            payment=self.payment, business=self.business, cloudinary_public_id='fake',
            resource_type='image', mime_type='image/png', file_size=100,
            reference_number='REF1', payment_date=date.today(),
        )
        reject_receipt(receipt, self.staff_user, 'Comprobante ilegible')
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, 'rejected')
        self.assertEqual(receipt.rejection_reason, 'Comprobante ilegible')


class StaffPanelAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        self.customer_client = TestClient()
        self.customer_user, self.business = _register_and_verify(self.customer_client, 'staffcheck@example.com', 'Staff Check Biz')

        support_role, _ = Role.objects.get_or_create(code=Role.SUPPORT, defaults={'name': 'Soporte'})
        self.support_user = User.objects.create_user(username='support@example.com', email='support@example.com', password='ClaveSegura123!')
        UserRole.objects.create(user=self.support_user, role=support_role)
        self.support_client = TestClient()
        self.support_client.force_login(self.support_user)

        admin_role, _ = Role.objects.get_or_create(code=Role.ADMIN, defaults={'name': 'Administrador'})
        self.admin_user = User.objects.create_user(username='adminuser@example.com', email='adminuser@example.com', password='ClaveSegura123!')
        UserRole.objects.create(user=self.admin_user, role=admin_role)
        self.admin_client = TestClient()
        self.admin_client.force_login(self.admin_user)

    def test_customer_without_role_forbidden(self):
        resp = self.customer_client.get(reverse('cotizador_app:staff_dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_support_can_view_but_not_edit_plans(self):
        self.assertEqual(self.support_client.get(reverse('cotizador_app:staff_dashboard')).status_code, 200)
        self.assertEqual(self.support_client.get(reverse('cotizador_app:staff_planes')).status_code, 403)

    def test_admin_can_edit_plans(self):
        self.assertEqual(self.admin_client.get(reverse('cotizador_app:staff_planes')).status_code, 200)


class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_t = TestClient()
        self.user, self.business = _register_and_verify(self.client_t, 'webhook@example.com', 'Webhook Biz')
        self.plan = SubscriptionPlan.objects.get(code='basic')
        self.payment = Payment.objects.create(business=self.business, plan=self.plan, provider=Payment.TILOPAY, amount=5000, currency='CRC')

    def test_duplicate_webhook_event_is_idempotent(self):
        from django.test import override_settings
        import json

        with override_settings(TILOPAY_WEBHOOK_SECRET='test-secret'):
            payload = json.dumps({
                'event_id': 'evt_dup_1', 'reference': self.payment.internal_reference, 'status': 'approved',
            })
            for _ in range(2):
                resp = self.client_t.post(
                    '/pagos/tilopay/webhook/', data=payload, content_type='application/json',
                    HTTP_X_TILOPAY_SIGNATURE='test-secret',
                )
                self.assertEqual(resp.status_code, 200)
            self.assertEqual(PaymentEvent.objects.filter(external_event_id='evt_dup_1').count(), 1)
            self.payment.refresh_from_db()
            self.assertEqual(self.payment.status, Payment.APPROVED)

    def test_bad_signature_rejected(self):
        from django.test import override_settings
        with override_settings(TILOPAY_WEBHOOK_SECRET='test-secret'):
            resp = self.client_t.post(
                '/pagos/tilopay/webhook/', data='{}', content_type='application/json',
                HTTP_X_TILOPAY_SIGNATURE='wrong-secret',
            )
            self.assertEqual(resp.status_code, 403)


class HealthEndpointTests(TestCase):
    def test_health_returns_200_ok(self):
        resp = TestClient().get('/health/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok'})
