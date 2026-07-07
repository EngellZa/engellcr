from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import auth, business, clients, products, quotations, billing, sinpe, gateway, staff

app_name = 'cotizador_app'

urlpatterns = [
    # Marketing
    path('', business.landing, name='landing'),

    # Auth
    path('registro/', auth.register, name='register'),
    path('login/', auth.CotizadorLoginView.as_view(), name='login'),
    path('logout/', auth.CotizadorLogoutView.as_view(), name='logout'),
    path('verificar-correo/<str:token>/', auth.verificar_correo, name='verificar_correo'),
    path('verificacion-pendiente/', auth.verificacion_pendiente, name='verificacion_pendiente'),
    path('verificacion-pendiente/reenviar/', auth.reenviar_verificacion, name='reenviar_verificacion'),

    path('password-reset/', auth.RateLimitedPasswordResetView.as_view(
        template_name='cotizador_app/password_reset_form.html',
        email_template_name='cotizador_app/emails/password_reset_email.html',
        success_url=reverse_lazy('cotizador_app:password_reset_done'),
    ), name='password_reset'),
    path('password-reset/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='cotizador_app/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/confirmar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='cotizador_app/password_reset_confirm.html',
        success_url=reverse_lazy('cotizador_app:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password-reset/completo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='cotizador_app/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Panel
    path('panel/', business.dashboard, name='dashboard'),
    path('panel/perfil-negocio/', business.perfil_negocio, name='perfil_negocio'),
    path('panel/ayuda/', business.ayuda, name='ayuda'),

    # Clientes
    path('panel/clientes/', clients.cliente_lista, name='cliente_lista'),
    path('panel/clientes/nuevo/', clients.cliente_crear, name='cliente_crear'),
    path('panel/clientes/<int:pk>/', clients.cliente_detalle, name='cliente_detalle'),
    path('panel/clientes/<int:pk>/editar/', clients.cliente_editar, name='cliente_editar'),
    path('panel/clientes/<int:pk>/eliminar/', clients.cliente_eliminar, name='cliente_eliminar'),

    # Productos y servicios
    path('panel/productos/', products.producto_lista, name='producto_lista'),
    path('panel/productos/nuevo/', products.producto_crear, name='producto_crear'),
    path('panel/productos/<int:pk>/editar/', products.producto_editar, name='producto_editar'),
    path('panel/productos/<int:pk>/archivar/', products.producto_archivar, name='producto_archivar'),

    # Cotizaciones
    path('panel/cotizaciones/', quotations.cotizacion_lista, name='cotizacion_lista'),
    path('panel/cotizaciones/nueva/', quotations.cotizacion_crear, name='cotizacion_crear'),
    path('panel/cotizaciones/<int:pk>/', quotations.cotizacion_detalle, name='cotizacion_detalle'),
    path('panel/cotizaciones/<int:pk>/editar/', quotations.cotizacion_editar, name='cotizacion_editar'),
    path('panel/cotizaciones/<int:pk>/eliminar/', quotations.cotizacion_eliminar, name='cotizacion_eliminar'),
    path('panel/cotizaciones/<int:pk>/duplicar/', quotations.cotizacion_duplicar, name='cotizacion_duplicar'),
    path('panel/cotizaciones/<int:pk>/pdf/', quotations.cotizacion_pdf, name='cotizacion_pdf'),
    path('panel/cotizaciones/<int:pk>/enviar/', quotations.cotizacion_enviar, name='cotizacion_enviar'),
    path('panel/cotizaciones/<int:pk>/compartir/', quotations.cotizacion_compartir, name='cotizacion_compartir'),

    # Plan y pagos
    path('panel/plan/', billing.plan_actual, name='plan_actual'),
    path('panel/plan/mejorar/', billing.plan_mejorar, name='plan_mejorar'),
    path('panel/pagos/', billing.pagos_lista, name='pagos_lista'),
    path('panel/pagos/iniciar/<int:plan_id>/<str:metodo>/', billing.pago_iniciar, name='pago_iniciar'),
    path('panel/pagos/sinpe/nuevo/<int:payment_id>/', sinpe.sinpe_subir_comprobante, name='sinpe_subir_comprobante'),
    path('panel/pagos/recibo/<int:receipt_id>/', sinpe.ver_recibo, name='ver_recibo'),
    path('panel/pagos/<str:metodo>/retorno/', gateway.pago_retorno, name='pago_retorno'),
    path('pagos/<str:metodo>/webhook/', gateway.pago_webhook, name='pago_webhook'),

    # Panel de administración (staff)
    path('staff/', staff.staff_dashboard, name='staff_dashboard'),
    path('staff/usuarios/', staff.staff_usuarios, name='staff_usuarios'),
    path('staff/negocios/', staff.staff_negocios, name='staff_negocios'),
    path('staff/negocios/<int:pk>/', staff.staff_negocio_detalle, name='staff_negocio_detalle'),
    path('staff/planes/', staff.staff_planes, name='staff_planes'),
    path('staff/suscripciones/', staff.staff_suscripciones, name='staff_suscripciones'),
    path('staff/suscripciones/<int:pk>/editar/', staff.staff_suscripcion_editar, name='staff_suscripcion_editar'),
    path('staff/pagos/', staff.staff_pagos, name='staff_pagos'),
    path('staff/pagos/<int:pk>/', staff.staff_pago_detalle, name='staff_pago_detalle'),
    path('staff/sinpe/', staff.staff_sinpe_cola, name='staff_sinpe_cola'),
    path('staff/sinpe/<int:pk>/revisar/', staff.staff_sinpe_revisar, name='staff_sinpe_revisar'),
    path('staff/auditoria/', staff.staff_auditoria, name='staff_auditoria'),
    path('staff/ayuda/', staff.staff_ayuda, name='staff_ayuda'),
]
