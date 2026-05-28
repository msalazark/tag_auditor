# Tag Audit Tool

Audita el etiquetado GTM / GA4 / dataLayer de cualquier URL ejecutando un browser real con Playwright.

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
# Auditoría básica (headless)
python main.py --url https://www.cementospacasmayo.com.pe/

# Con browser visible y spec personalizada
python main.py --url https://example.com --headless false --spec specs/custom_spec.json

# Más tiempo de espera para SPAs lentas
python main.py --url https://example.com --timeout 8
```

## Flags

| Flag        | Default                    | Descripción                                   |
|-------------|----------------------------|-----------------------------------------------|
| `--url`     | requerido                  | URL a auditar                                 |
| `--spec`    | `specs/default_spec.json`  | Path al JSON de spec de eventos esperados     |
| `--headless`| `true`                     | Modo headless del browser (`true`/`false`)    |
| `--timeout` | `3`                        | Segundos extra de espera tras networkidle     |
| `--output`  | `reports`                  | Carpeta de output para reportes               |

## Qué detecta

- **GTM containers**: IDs (`GTM-XXXXXXX`) y versiones vía `window.google_tag_manager`
- **GA4 Measurement IDs** (`G-XXXXXXX`): desde scripts, dataLayer y hits de red
- **Hits GA4**: interceptados en `analytics.google.com/g/collect` con sus parámetros
- **Otros pixels**: Meta Pixel, TikTok, LinkedIn Insight, Twitter, Google Ads
- **dataLayer pushes**: cada `window.dataLayer.push()` con timestamp y parámetros completos
- **Interacciones**: scroll 25/50/75/100%, primer CTA visible, focus en formulario

## Estructura de la spec

```json
{
  "events": [
    {
      "name": "page_view",
      "trigger": "page_load",
      "required_params": ["page_title", "page_location"],
      "priority": "P1"
    }
  ]
}
```

**Estados de validación**: `OK` (evento presente con todos los params) · `PARCIAL` (presente, faltan params) · `AUSENTE`

## Output

Cada ejecución genera dos archivos en `reports/`:

- `{domain}_{timestamp}.html` — reporte standalone (sin dependencias externas)
- `{domain}_{timestamp}.json` — data estructurada completa

## Stack

- [Playwright](https://playwright.dev/python/) — browser automation
- [Click](https://click.palletsprojects.com/) — CLI
