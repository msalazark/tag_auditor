# Tag Audit Tool

Herramienta de auditoría de etiquetado GA4/GTM con Playwright. Cubre desde la validación de una URL puntual contra una spec hasta el análisis de oportunidades de tagging con IA en sitios completos.

---

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

**Variables de entorno necesarias para funciones IA:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # requerido solo para tag-plan
```

---

## Comandos disponibles

### 1. `main.py` — Auditoría de URL única con spec

Valida una URL específica contra una spec JSON personalizada. Genera reporte HTML con score P1, brechas y timeline de dataLayer.

```bash
python main.py --url https://sitio.com/ --spec specs/example_corporate.json
python main.py --url https://tienda.com --spec specs/example_ecommerce.json --headless false
python main.py --url https://sitio.com --spec specs/example_leadgen.json --timeout 5
```

| Flag | Default | Descripción |
|---|---|---|
| `--url` | requerido | URL a auditar |
| `--spec` | requerido | Path al JSON de spec |
| `--headless` | `true` | Modo headless del browser |
| `--timeout` | `3` | Segundos extra de espera |
| `--output` | `reports` | Carpeta de output |

---

### 2. `site_main.py` — CLI multi-modal

```
python site_main.py <comando> [opciones]
```

#### `audit` — Crawl site-wide automático

Descubre URLs (sitemap → robots.txt → crawl), clasifica journeys y ejecuta la auditoría en todas las páginas.

```bash
python site_main.py audit --url www.sitio.com
python site_main.py audit --url www.sitio.com --headless false --timeout 5
python site_main.py audit --url www.sitio.com --auth auth/configs/mi_auth.json
python site_main.py audit --url www.sitio.com --save-plan
```

| Flag | Default | Descripción |
|---|---|---|
| `--url` | requerido | Dominio raíz |
| `--headless` | `true` | Modo headless |
| `--timeout` | `3` | Segundos de espera por página |
| `--output` | `reports` | Carpeta de output |
| `--save-plan` | `false` | Guardar plan de journeys en JSON |
| `--auth` | — | Config de auth para sitios con login |

---

#### `assisted` — Auditoría con navegación manual

Abre el browser visible con todos los instrumentos activos. El auditor navega libremente mientras el sistema captura dataLayer + GA4 + pixels en tiempo real.

```bash
# Sitio público
python site_main.py assisted --url https://construyexperto.pe

# Sitio con login previo
python site_main.py assisted --url https://construyexperto.pe --auth auth/configs/construyexperto_auth.json
```

**Flujo:**
1. Browser se abre en la URL indicada
2. Si hay sesión, carga automáticamente
3. El auditor navega (puede hacer login manual, explorar secciones)
4. Terminal muestra en tiempo real: `URL | dl:12 | ga4:8 | px:3`
5. ENTER → sesión guardada + reporte JSON + HTML generado

| Flag | Default | Descripción |
|---|---|---|
| `--url` | requerido | URL de inicio |
| `--auth` | — | Config de auth para cargar/guardar sesión |
| `--output` | `reports` | Carpeta de output |
| `--save-session` | — | Path alternativo para guardar sesión |

---

#### `batch` — Auditoría desde lista de URLs

Ejecuta la auditoría en una lista de URLs definida en archivo `.txt` o `.csv`.

```bash
python site_main.py batch --urls mis_urls.txt
python site_main.py batch --urls mis_urls.csv --headless false --timeout 5
python site_main.py batch --urls mis_urls.txt --auth auth/configs/mi_auth.json
```

**Formato `.txt`** (una URL por línea, `#` para comentarios):
```
https://sitio.com/
https://sitio.com/productos
# https://sitio.com/ignorar
```

**Formato `.csv`** (url, tipo, nombre opcionales):
```
https://sitio.com/,home,Home
https://sitio.com/productos,product,Catálogo
https://sitio.com/contacto,contact,Contacto
```

| Flag | Default | Descripción |
|---|---|---|
| `--urls` | requerido | Archivo `.txt` o `.csv` |
| `--headless` | `true` | Modo headless |
| `--timeout` | `3` | Segundos por página |
| `--output` | `reports` | Carpeta de output |
| `--auth` | — | Config de auth |

---

#### `auth-only` — Login aislado

Autentica en el sitio y guarda la sesión sin ejecutar auditoría. Útil para renovar sesiones antes de un audit programado.

```bash
python site_main.py auth-only --auth auth/configs/mi_auth.json
python site_main.py auth-only --auth auth/configs/mi_auth.json --notification desktop
```

| Notification mode | Comportamiento |
|---|---|
| `terminal` (default) | Countdown en consola, ENTER para continuar |
| `desktop` | Notificación nativa del SO + terminal |
| `webhook` | POST JSON con screenshot base64 a URL externa |

---

#### `tag-plan` — Análisis de oportunidades con IA

Crawlea el sitio o visita una lista de URLs, extrae elementos interactivos y usa Claude API para identificar oportunidades de tagging GA4/GTM con esfuerzo y valor de negocio.

```bash
# Desde lista de URLs
python site_main.py tag-plan --urls-file urls_cliente.txt

# Crawl automático desde raíz
python site_main.py tag-plan --url https://www.sitio.com --pages 15

# Especificar modelo y saltar confirmación
python site_main.py tag-plan --urls-file urls.txt --model claude-sonnet-4-6 --yes
```

**Flujo:**
1. Visita las páginas y extrae botones, links, formularios y CTAs
2. Cuenta tokens vía API y muestra estimación de costo **antes** de analizar
3. Pide confirmación (saltar con `--yes`)
4. Analiza cada página con Claude → backlog priorizado
5. Genera reporte HTML con matriz esfuerzo/valor

**Ejemplo de estimación de costo:**
```
  Páginas a analizar    : 27
  Tokens input (total)  : 54,000
  Tokens output (est.)  : 12,150

  Costo estimado por modelo:
    Haiku 4.5   — rápido, costo muy bajo             $0.11 USD
    Sonnet 4.6  — balance calidad/costo (recomendado) $0.34 USD  <-- seleccionado
    Opus 4.7    — máxima calidad                     $0.57 USD

  ¿Continuar con el análisis? [s/N]:
```

| Flag | Default | Descripción |
|---|---|---|
| `--url` | — | URL raíz para crawl automático |
| `--urls-file` | — | Archivo `.txt`/`.csv` con URLs específicas |
| `--pages` | `10` | Máximo de páginas (solo con `--url`) |
| `--model` | `claude-opus-4-7` | Modelo Claude para el análisis |
| `--headless` | `true` | Modo headless |
| `--output` | `reports` | Carpeta de output |
| `--auth` | — | Config de auth para sitios con login |
| `-y, --yes` | `false` | Saltar confirmación de costo |
| `--api-key` | `$ANTHROPIC_API_KEY` | API key de Anthropic |

**Reporte generado incluye:**
- KPIs ejecutivos: P1/P2/P3, horas totales, quick wins
- Matriz 2×2 Esfuerzo/Valor: Quick Wins / Proyectos Estratégicos / Fill-ins / Reconsiderar
- Backlog priorizado con event_name, trigger GTM, parámetros y esfuerzo
- Detalle por página con contexto de negocio

---

#### `report` — Generar HTML desde JSON

Convierte cualquier JSON de resultado en un reporte HTML standalone.

```bash
# Desde auditoría asistida
python site_main.py report reports/construyexperto_pe_assisted_20260528.json

# Desde crawl site-wide
python site_main.py report reports/site_audit_results.json

# Output en carpeta específica
python site_main.py report reports/mis_datos.json --output /tmp/reportes
```

Detecta automáticamente el formato (`mode: "assisted"` o presencia de `journeys`).

---

## Módulo de Autenticación (`auth/`)

Para auditar sitios que requieren login.

### Estrategias soportadas

| Estrategia | Cuándo usarla |
|---|---|
| `form_login` | Login automatizable (usuario+password ± OTP/2FA) |
| `session_inject` | Login complejo (modal, celular+SMS, SSO) — sesión exportada manualmente |
| `token_header` | APIs o SPAs con Bearer token |

### Detección automática de bloqueos

`form_login` detecta y pausa automáticamente ante:
- CAPTCHA (reCAPTCHA, hCAPTCHA, Cloudflare Turnstile)
- OTP por SMS o email
- Push notification / aprobación en app
- SSO externo (Google, Microsoft, Okta, etc.)
- Pregunta de seguridad
- Hardware key (YubiKey, WebAuthn)

Cuando detecta un bloqueo: toma screenshot, notifica al auditor y espera (con countdown visible).

### Configs de ejemplo

```
auth/configs/
├── example_form_simple.json      # usuario+password sin 2FA
├── example_form_otp.json         # con OTP por SMS
├── example_form_sso.json         # con Google/Microsoft SSO
├── example_token_header.json     # Bearer token
└── example_session_inject.json   # sesión exportada manualmente
```

### Config básica

```json
{
  "domain": "mi-sitio.com",
  "strategy": "form_login",
  "login_url": "https://mi-sitio.com/login",
  "may_require_interaction": true,
  "notification_mode": "desktop",
  "interaction_timeout": 180,
  "credentials_env": {
    "username": "AUDIT_USER",
    "password": "AUDIT_PASS"
  },
  "session_file": "auth/sessions/mi_sitio_session.json",
  "session_ttl_hours": 8
}
```

### Exportar sesión manualmente

Para sitios con login imposible de automatizar (modal + celular + OTP):

```bash
python auth/export_session.py https://mi-sitio.com auth/sessions/mi_sesion.json
```

Abre browser visible, el auditor hace login completo, ENTER → sesión guardada.

### Flujo recomendado para sitios con auth compleja

```bash
# 1. Guardar sesión (una vez, válida ~8 horas)
python auth/export_session.py https://construyexperto.pe auth/sessions/construyexperto_session.json

# 2. Auditoría asistida con sesión cargada
python site_main.py assisted --url https://construyexperto.pe --auth auth/configs/construyexperto_auth.json

# 3. O auditoría automática site-wide
python site_main.py audit --url construyexperto.pe --auth auth/configs/construyexperto_auth.json
```

---

## Specs de validación (`specs/`)

Para `main.py` — validan el tagging contra un checklist definido por el cliente.

```json
{
  "site": "mi-sitio.com",
  "client": "Nombre Cliente",
  "version": "1.0",
  "events": [
    {
      "category": "ecommerce",
      "name": "view_item",
      "description": "Vista de producto",
      "trigger": "Carga de página de producto",
      "priority": "P1",
      "source": "dataLayer",
      "required_params": [
        {"key": "event", "type": "string", "example": "view_item"},
        {"key": "ecommerce.items[0].item_id", "type": "string"}
      ],
      "optional_params": []
    }
  ]
}
```

| Campo | Valores |
|---|---|
| `category` | `ecommerce`, `leads`, `custom` |
| `source` | `dataLayer`, `ga4_hit`, `both` |
| `priority` | `P1` (crítico), `P2` (importante), `P3` (nice-to-have) |
| tipos de param | `string`, `number`, `boolean`, `array`, `object` |

Specs incluidas: `example_ecommerce.json`, `example_leadgen.json`, `example_corporate.json`

---

## Qué detecta en cada auditoría

- **GTM containers**: IDs (`GTM-XXXXXXX`) vía `window.google_tag_manager`
- **GA4 Measurement IDs** (`G-XXXXXXX`): desde scripts, dataLayer y hits de red
- **Hits GA4**: interceptados en `analytics.google.com/g/collect` con todos los parámetros parseados
- **Pixels de terceros**: Meta Pixel, TikTok, LinkedIn Insight, Twitter/X, Google Ads, Hotjar, Microsoft Clarity
- **Consent Mode v2**: eventos `consent_default` y `consent_update` con estado de cada storage
- **dataLayer pushes**: cada `window.dataLayer.push()` con timestamp e índice
- **SPA navigation**: `gtm.historyChange-v2` en Angular/React/Vue (pushState)
- **Interacciones GTM**: linkClick, scrollDepth, formSubmit

---

## Output de cada comando

| Comando | Archivos generados |
|---|---|
| `main.py` | `reports/{domain}_{ts}.html` + `.json` |
| `audit` | `reports/site_audit_results.json` → `report` para el HTML |
| `assisted` | `reports/{domain}_assisted_{ts}.json` + HTML vía `report` |
| `batch` | `reports/{domain}_batch_{ts}.json` + HTML automático |
| `tag-plan` | `reports/{domain}_tag_plan_{ts}.html` + `.json` |

---

## Estructura del proyecto

```
tag_auditor/
├── main.py                     # Auditoría URL única con spec
├── site_main.py                # CLI multi-modal (audit, assisted, batch, tag-plan, report, auth-only)
├── auditor.py                  # Motor de auditoría + ReportGenerator
├── tagging_planner.py          # Crawler de elementos + análisis IA con Claude
│
├── auth/                       # Módulo de autenticación
│   ├── session_manager.py      # Orquestador de estrategias (form_login, token, inject)
│   ├── interactive_auth.py     # Detección de 2FA/OTP/CAPTCHA/SSO + espera humana
│   ├── export_session.py       # Exportación manual de sesiones
│   ├── sessions/               # Sesiones guardadas (.gitignore)
│   ├── screenshots/            # Screenshots tomados en pausa (.gitignore)
│   └── configs/                # Configs de ejemplo por estrategia
│
├── modules/
│   ├── datalayer_recorder.py   # Proxy JS para window.dataLayer
│   ├── ga4_interceptor.py      # Interceptor de hits GA4 y pixels
│   ├── gtm_inspector.py        # Inspector de containers GTM
│   ├── interaction_simulator.py
│   ├── report_generator.py     # Generador HTML (spec-based)
│   ├── spec_validator.py       # Validador de spec
│   ├── assisted_report.py      # Reporte HTML modo asistido
│   ├── site_audit_report.py    # Reporte HTML site-wide
│   └── tagging_report.py       # Reporte HTML tag-plan con matriz esfuerzo/valor
│
├── runners/
│   ├── static_runner.py        # Journey de páginas estáticas
│   ├── ecommerce_runner.py     # Journey e-commerce (product → cart → checkout)
│   └── lead_runner.py          # Journey lead gen (fill form → submit)
│
├── specs/                      # Specs de validación por tipo de sitio
│   ├── default_spec.json
│   ├── example_corporate.json
│   ├── example_ecommerce.json
│   └── example_leadgen.json
│
└── reports/                    # Output generado (en .gitignore)
```

---

## Stack

- [Playwright](https://playwright.dev/python/) — automatización de browser
- [Click](https://click.palletsprojects.com/) — CLI
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) — análisis IA con Claude
- [Pydantic](https://docs.pydantic.dev/) — structured output del análisis
- [jsonschema](https://python-jsonschema.readthedocs.io/) — validación de specs
- [Jinja2](https://jinja.palletsprojects.com/) — templates HTML
- [aiohttp](https://docs.aiohttp.org/) — modo webhook en auth interactiva
