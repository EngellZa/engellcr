# 🧾 Cotización Express CR

SaaS para pequeños negocios en Costa Rica/LatAm:
- **Cotizaciones profesionales en PDF** con logo y marca del negocio
- **Envío por correo o WhatsApp** con un solo clic
- **Clientes y productos/servicios** organizados
- **Enlace público** de cotización (el cliente puede aprobar/rechazar)
- **Suscripción mensual** — Prueba Gratis, Básico, Pro, Business
- **Pago por SINPE Móvil** (manual, con aprobación de admin) — arquitectura lista para Tilopay/PayPal
- Listo para **Railway + Docker**, con **Cloudinary** para logos, PDFs y comprobantes

---

## 🗂️ Estructura del proyecto

```
├── config/                  # Configuración Django
│   ├── settings.py
│   ├── urls.py
│   ├── views.py             # /health/
│   └── wsgi.py
├── cotizador_app/           # App principal (todo el producto vive acá)
│   ├── migrations/
│   ├── templates/cotizador_app/
│   ├── models.py             # Business, Client, Product, Quotation, Subscription, Payment, ...
│   ├── views/                 # auth, business, clients, products, quotations, share, billing, sinpe, staff
│   ├── payments/                # abstracción de pago: base, tilopay, paypal, sinpe
│   ├── services.py               # totales, numeración de cotizaciones, cuotas, activación de suscripción
│   ├── pdf.py                     # generación de PDF (WeasyPrint) con reuso por hash de contenido
│   ├── cache.py / ratelimit.py     # cache (Redis opcional) y rate limiting
│   ├── emailing.py                  # envío de correo + verificación de cuenta
│   ├── decorators.py                 # cotizador_login_required, role_required, get_current_business
│   ├── forms.py, admin.py, urls.py
│   └── templatetags/
├── Dockerfile
├── requirements.txt
├── .env.example
└── manage.py
```

---

## 🚀 Correr en local

### 1. Crear entorno virtual e instalar dependencias
```bash
python -m venv venv
source venv/bin/activate       # Linux/Mac
venv\Scripts\activate          # Windows

pip install -r requirements.txt
```

> **Windows:** usá un Python nativo de Windows (no un Python de MSYS2/mingw) — `psycopg2-binary`, `Pillow` y `weasyprint` necesitan wheels precompilados que un Python mingw no puede resolver.

### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tus datos
```

Para pruebas locales con SQLite, en `.env` alcanza con:
```env
DEBUG=True
SECRET_KEY=cualquier-clave
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
```
El resto de variables (Cloudinary, correo, Redis, Tilopay, PayPal, SINPE, WhatsApp) son opcionales en local — todo tiene un fallback seguro (ver [Variables de entorno](#-variables-de-entorno)).

### 3. Migraciones
```bash
python manage.py migrate
```
La migración de datos `cotizador_app.0002_seed_roles_plans` crea automáticamente los 3 roles (`customer`/`admin`/`support`) y los 4 planes (Prueba Gratis, Básico, Pro, Business). Para tener un usuario admin del panel `staff/`, registrate normalmente en `/registro/` y luego asignale el rol `admin` desde `/admin/` (modelo `UserRole`).

### 4. Correr servidor
```bash
python manage.py runserver
```
Abrí `http://localhost:8000/` — esa es la landing page pública. `/registro/` para crear cuenta, `/login/` para iniciar sesión, `/panel/` es el dashboard (requiere sesión + correo verificado).

---

## 🌐 Rutas principales

| Ruta | Descripción |
|------|-------------|
| `/` | Landing page |
| `/registro/`, `/login/`, `/logout/` | Autenticación |
| `/verificacion-pendiente/` | Bloqueo hasta verificar correo |
| `/panel/` | Dashboard |
| `/panel/perfil-negocio/` | Perfil de negocio (onboarding + edición) |
| `/panel/clientes/`, `/panel/productos/`, `/panel/cotizaciones/` | CRUD del negocio |
| `/panel/plan/`, `/panel/pagos/` | Plan, uso y pagos |
| `/q/<token>/` | Enlace público de cotización (sin login) |
| `/staff/` | Panel de administración (roles `admin`/`support`) |
| `/admin/` | Panel de administración Django (soporte técnico/DB) |
| `/health/` | Health check para Railway (sin dependencias) |

---

## 🔐 Variables de entorno

Ver [.env.example](.env.example) para la lista completa con comentarios. Resumen de qué pasa si dejás cada grupo vacío:

| Grupo | Sin configurar |
|-------|----------------|
| `REDIS_URL` | Usa cache en memoria local (funciona, pero no se comparte entre workers) |
| `EMAIL_HOST` | Los correos se imprimen en la consola en vez de enviarse |
| `CLOUDINARY_*` | Los archivos se guardan localmente (no recomendado en Railway) |
| `TILOPAY_*` / `PAYPAL_*` | Botones de pago visibles pero no funcionales (arquitectura lista, sin credenciales reales) |
| `SINPE_MOBILE_NUMBER` / `SINPE_ACCOUNT_HOLDER` | La pantalla de pago SINPE no muestra datos de cuenta |
| `WHATSAPP_CONTACT_NUMBER` | El botón de WhatsApp no se muestra en la landing |

---

## 🚂 Deploy en Railway

### 1. Subir a GitHub y crear proyecto en Railway
- Nueva app desde el repo de GitHub
- Agregar servicio **PostgreSQL** (Railway lo configura solo)
- Agregar servicio **Redis** (opcional, recomendado para cache/rate-limit exactos en producción)

### 2. Variables de entorno en Railway
Copiá las de `.env.example`, además de:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```

### 3. El Dockerfile se usa automáticamente
El `CMD` incluye:
```bash
python manage.py migrate --noinput && \
python manage.py collectstatic --noinput && \
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

### 4. Health check
Configurá el health check path de Railway en `/health/` (no depende de DB/cache/Cloudinary).

### 5. Crear un usuario admin del panel `staff/`
Registrate normalmente en `/registro/`, verificá el correo, y asignale el rol `admin` vía `/admin/` → `UserRole`.

---

## ✅ Checklist de seguridad (mínimo viable)

- Contraseñas con hashing de Django (nunca en texto plano)
- Verificación de correo bloqueante antes de usar la app
- Rate limiting en login, registro, reset de contraseña, subida de comprobantes y pagos
- Aislamiento de datos por negocio: toda vista de cliente filtra por `business` del usuario logueado
- Panel `staff/` protegido por rol explícito (`UserRole`), no por `is_staff`
- Comprobantes SINPE: validación server-side de tamaño/tipo (magic bytes, no solo extensión), almacenamiento privado en Cloudinary (`type=authenticated`), servidos solo vía URL firmada de corta duración
- Webhooks de pago verificados por firma + idempotencia (`PaymentEvent` único por `provider`+`external_event_id`)
- Cookies seguras/HttpOnly, CSRF, HSTS y cabeceras de seguridad en producción (`DEBUG=False`)

## ⚡ Checklist de rendimiento

- Listas de clientes/productos/cotizaciones/pagos paginadas
- Índices de base de datos en los campos de filtro más usados (`business`+`created_at`, `status`, `quote_number`, `internal_reference`, tokens públicos)
- PDF de cotización se regenera solo si el contenido cambió (hash de contenido), nunca en cada carga del dashboard
- Cache opcional (Redis) con claves determinísticas, sin dependencia obligatoria
- `/health/` no toca DB/cache/Cloudinary — respuesta rápida y confiable para el health check de Railway

---

## 🧪 Tests

```bash
python manage.py test cotizador_app
```

24 tests cubren los flujos críticos: registro/trial, aislamiento de datos entre negocios, límite de cotizaciones, cálculo de totales, generación de PDF (con reuso por hash), seguridad de enlaces públicos, validación de comprobantes SINPE (tamaño/tipo), aprobación de pagos, permisos del panel `staff/` por rol, idempotencia de webhooks, y el health check.

> **Nota:** requiere una base de datos de test (Django crea/destruye `test_<nombre_db>` automáticamente). Si usás Postgres remoto, esto puede tardar 1-2 minutos por la latencia de red — usá `--keepdb` en corridas repetidas para saltarte la recreación de esquema.

## 🛠️ Troubleshooting

| Problema | Causa / Solución |
|----------|-------------------|
| `psycopg2`/`Pillow`/`weasyprint` fallan al instalar en Windows | Estás usando un Python de MSYS2/mingw. Instalá un Python nativo de Windows (`py install 3.12`) y creá el venv con ese. |
| El navegador muestra "connection is not secure" / `ERR_SSL_PROTOCOL_ERROR` en local | El navegador está forzando HTTPS sobre `127.0.0.1`/`localhost`, pero `manage.py runserver` solo sirve HTTP. Escribí `http://127.0.0.1:8000` explícitamente, o limpiá la política HSTS guardada para ese host en tu navegador. |
| `AttributeError: 'super' object has no attribute 'dicts'` al correr `manage.py test` | Incompatibilidad de Django 5.0.6 con Python 3.14+ en la instrumentación de templates del test runner. Usá Python 3.12 (el mismo que corre en producción vía Docker). |
| Error `Must supply api_key` al subir un archivo | Faltan `CLOUDINARY_CLOUD_NAME`/`CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` en `.env`. Sin Cloudinary, los archivos caen a almacenamiento local (`MEDIA_ROOT`), pero los comprobantes SINPE privados sí requieren Cloudinary configurado. |
| `manage.py test` falla la primera vez con "database already exists" o "being accessed by other users" | Una corrida anterior quedó a medias. Terminá las conexiones y recreá: conectate a la DB y corré `DROP DATABASE test_<nombre>;`, o simplemente reintentá — Django limpia la DB de test al finalizar una corrida exitosa. |

---

## 📌 Estado actual

Este producto reemplazó a la app anterior de este repositorio ("Finanzas Personales", eliminada). Todas las fases del MVP (registro/trial, clientes/productos/cotizaciones, PDF/correo/WhatsApp, planes, SINPE, arquitectura Tilopay/PayPal, panel `staff/`, cache/rate-limiting/seguridad) están implementadas y verificadas — 24/24 tests automatizados pasando. Pendiente antes de producción: credenciales reales de Tilopay/PayPal (arquitectura ya lista), número real de WhatsApp/SINPE en variables de entorno, y el primer deploy a Railway.
