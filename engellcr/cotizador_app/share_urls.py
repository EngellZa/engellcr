from django.urls import path

from .views import share

urlpatterns = [
    path('<str:token>/', share.public_quote_view, name='public_quote_view'),
    path('<str:token>/aprobar/', share.public_quote_approve, name='public_quote_approve'),
    path('<str:token>/rechazar/', share.public_quote_reject, name='public_quote_reject'),
    path('<str:token>/orden-compra/', share.public_quote_subir_orden, name='public_quote_subir_orden'),
]
