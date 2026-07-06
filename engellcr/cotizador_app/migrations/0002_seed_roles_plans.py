from django.db import migrations


def seed_roles_and_plans(apps, schema_editor):
    Role = apps.get_model('cotizador_app', 'Role')
    SubscriptionPlan = apps.get_model('cotizador_app', 'SubscriptionPlan')

    roles = [
        ('customer', 'Cliente'),
        ('admin', 'Administrador'),
        ('support', 'Soporte'),
    ]
    for code, name in roles:
        Role.objects.get_or_create(code=code, defaults={'name': name})

    plans = [
        ('free_trial', 'Prueba Gratis', 0, 3),
        ('basic', 'Básico', 5000, 20),
        ('pro', 'Pro', 10000, 100),
        ('business', 'Business', 20000, None),
    ]
    for code, name, price, limit in plans:
        SubscriptionPlan.objects.get_or_create(
            code=code,
            defaults={'name': name, 'price_crc': price, 'monthly_quote_limit': limit, 'is_active': True},
        )


def unseed_roles_and_plans(apps, schema_editor):
    Role = apps.get_model('cotizador_app', 'Role')
    SubscriptionPlan = apps.get_model('cotizador_app', 'SubscriptionPlan')
    Role.objects.filter(code__in=['customer', 'admin', 'support']).delete()
    SubscriptionPlan.objects.filter(code__in=['free_trial', 'basic', 'pro', 'business']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cotizador_app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_roles_and_plans, unseed_roles_and_plans),
    ]
