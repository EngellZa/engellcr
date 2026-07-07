from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils import timezone

from ..decorators import cotizador_login_required, get_current_business
from ..emailing import send_verification_email, read_verification_token
from ..forms import RegistroForm, CotizadorLoginForm
from ..models import UserProfile
from ..ratelimit import rate_limit
from ..services import create_trial_business


class CotizadorLoginView(LoginView):
    template_name = 'cotizador_app/login.html'
    authentication_form = CotizadorLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('cotizador_app:dashboard')

    @rate_limit('login', limit=5, window_seconds=300)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CotizadorLogoutView(LogoutView):
    next_page = reverse_lazy('cotizador_app:login')


class RateLimitedPasswordResetView(PasswordResetView):
    @rate_limit('password_reset', limit=3, window_seconds=3600)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@rate_limit('register', limit=5, window_seconds=3600)
def register(request):
    if request.user.is_authenticated:
        return redirect('cotizador_app:dashboard')

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                email = form.cleaned_data['email']
                user = User.objects.create_user(
                    username=email, email=email,
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['full_name'][:150],
                )
                UserProfile.objects.create(user=user)
                business = create_trial_business(user, form.cleaned_data['business_name'])
            auth_login(request, user)
            send_verification_email(request, user, business=business)
            messages.success(request, 'Cuenta creada. Revisá tu correo para verificar tu cuenta.')
            return redirect('cotizador_app:verificacion_pendiente')
    else:
        form = RegistroForm()
    return render(request, 'cotizador_app/register.html', {'form': form})


@cotizador_login_required
def verificacion_pendiente(request):
    profile = request.user.cotizador_profile
    if profile.email_verified:
        return redirect('cotizador_app:dashboard')
    return render(request, 'cotizador_app/verificacion_pendiente.html')


@cotizador_login_required
@rate_limit('reenviar_verificacion', limit=3, window_seconds=3600, key_kind='user')
def reenviar_verificacion(request):
    profile = request.user.cotizador_profile
    if not profile.email_verified:
        send_verification_email(request, request.user, business=get_current_business(request))
        messages.success(request, 'Te reenviamos el correo de verificación.')
    return redirect('cotizador_app:verificacion_pendiente')


def verificar_correo(request, token):
    user_id = read_verification_token(token)
    if user_id is None:
        messages.error(request, 'El enlace de verificación no es válido o expiró.')
        return redirect('cotizador_app:login')

    try:
        profile = UserProfile.objects.select_related('user').get(user_id=user_id)
    except UserProfile.DoesNotExist:
        messages.error(request, 'El enlace de verificación no es válido.')
        return redirect('cotizador_app:login')

    if not profile.email_verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    messages.success(request, '¡Correo verificado! Ya podés usar Cotización Express.')

    # The signed token already proves ownership of this account, so log the user in
    # directly here instead of bouncing them to a manual login (this is what makes the
    # emailed link work even when opened in a browser/device with no existing session).
    if not (request.user.is_authenticated and request.user.id == user_id):
        auth_login(request, profile.user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('cotizador_app:dashboard')
