# Tag Audit Tool

Audita el etiquetado GTM / GA4 / dataLayer de cualquier URL ejecutando un browser real con Playwright y validando 100% contra una spec JSON personalizada.

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
python main.py --url https://www.cementospacasmayo.com.pe/ --spec specs/example_corporate.json
python main.py --url https://tienda.ejemplo.com --spec specs/example_ecommerce.json --headless false
python main.py --url https://ejemplo.com --spec specs/example_leadgen.json --timeout 5
```

## Flags

| Flag        | Default   | Descripción                                                      |
|-------------|-----------|------------------------------------------------------------------|
| `--url`     | requerido | URL a auditar                                                    |
| `--spec`    | requerido | Path al JSON de spec personalizado                                |
| `--headless`| `true`    | Modo headless del browser (`true`/`false`)                       |
| `--timeout` | `3`       | Segundos extra de espera tras `networkidle`                      |
| `--output`  | `reports` | Carpeta de output para reportes                                  |

## Estructura de la spec

La spec debe ser un JSON válido con metadata y un arreglo de eventos.

```json
{
  "site": "nombre-del-sitio.com",
  "client": "Nombre del Cliente",
  "version": "1.0",
  "events": [
    {
      "category": "ecommerce",
      "name": "view_item",
      "description": "Vista de página de producto",
      "trigger": "Cuando el usuario carga la página de un producto",
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

### Categorías disponibles

- `ecommerce`
- `leads`
- `custom`

### Fuentes soportadas

- `dataLayer`
- `ga4_hit`
- `both`

### Tipos de parámetro

- `string`
- `number`
- `boolean`
- `array`
- `object`

## Qué detecta

- **GTM containers**: IDs (`GTM-XXXXXXX`) y versiones vía `window.google_tag_manager`
- **GA4 Measurement IDs** (`G-XXXXXXX`): desde scripts, `dataLayer` y hits de red
- **Hits GA4**: interceptados en `analytics.google.com/g/collect`
- **Otros pixels**: Meta Pixel, TikTok, LinkedIn Insight, Twitter, Google Ads
- **dataLayer pushes**: cada `window.dataLayer.push()` con timestamp y parámetros completos
- **Interacciones**: scroll 25/50/75/100%, clics en selectores relevantes, focus en formularios

## Output

Cada ejecución genera dos archivos en `reports/`:

- `{domain}_{timestamp}.html` — reporte standalone sin dependencias externas
- `{domain}_{timestamp}.json` — data estructurada completa

## Ejemplos de specs

- `specs/example_ecommerce.json`
- `specs/example_leadgen.json`
- `specs/example_corporate.json`

## Stack

- [Playwright](https://playwright.dev/python/) — browser automation
- [Click](https://click.palletsprojects.com/) — CLI
- [jsonschema](https://python-jsonschema.readthedocs.io/) — validación de spec
