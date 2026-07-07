from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import Business, Client, Product, Quotation, QuotationItem


class RegistroForm(forms.Form):
    full_name = forms.CharField(label='Nombre completo', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control'}))
    business_name = forms.CharField(label='Nombre del negocio', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('Ya existe una cuenta con este correo.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') and cleaned.get('confirm_password'):
            if cleaned['password'] != cleaned['confirm_password']:
                raise ValidationError('Las contraseñas no coinciden.')
        return cleaned


class CotizadorLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autofocus': True}))
    password = forms.CharField(label='Contraseña', strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}))


class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'legal_id', 'email', 'phone', 'address', 'logo',
                  'color_primary', 'currency', 'footer_note',
                  'sinpe_number', 'sinpe_account_holder']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'legal_id': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'color_primary': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'footer_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'sinpe_number': forms.TextInput(attrs={'class': 'form-control'}),
            'sinpe_account_holder': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'company_name', 'email', 'phone', 'identification', 'address', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'identification': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'sku', 'unit_price', 'tax_pct', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['client', 'issue_date', 'valid_until', 'currency', 'notes', 'terms']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields['client'].queryset = Client.objects.filter(business=business, is_deleted=False)


class ProductSelect(forms.Select):
    """Adds data-price/data-tax attrs to each <option> so the quotation form can
    auto-fill an item's price/tax via JS when a product is picked."""
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        raw_value = value.value if hasattr(value, 'value') else value
        if raw_value:
            product = Product.objects.filter(pk=raw_value).first()
            if product:
                option['attrs']['data-price'] = str(product.unit_price)
                option['attrs']['data-tax'] = str(product.tax_pct)
        return option


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ['product', 'description', 'quantity', 'unit_price', 'discount_pct', 'tax_pct']
        widgets = {
            'product': ProductSelect(attrs={'class': 'form-select form-select-sm item-product'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-qty', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-price', 'step': '0.01'}),
            'discount_pct': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-discount', 'step': '0.01'}),
            'tax_pct': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-tax', 'step': '0.01'}),
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields['product'].queryset = Product.objects.filter(business=business, is_active=True)
        self.fields['product'].required = False


QuotationItemFormSet = inlineformset_factory(
    Quotation, QuotationItem, form=QuotationItemForm,
    extra=1, can_delete=True, min_num=1, validate_min=True,
)


class SinpeReceiptForm(forms.Form):
    comprobante = forms.FileField(
        label='Comprobante (imagen o PDF)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
    )
    reference_number = forms.CharField(
        label='Referencia SINPE', max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    payment_date = forms.DateField(
        label='Fecha de pago',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    note = forms.CharField(
        label='Nota (opcional)', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def clean_comprobante(self):
        from .validators import validate_receipt_file
        file = self.cleaned_data['comprobante']
        mime_type, resource_type = validate_receipt_file(file)
        self.cleaned_data['mime_type'] = mime_type
        self.cleaned_data['resource_type'] = resource_type
        return file
