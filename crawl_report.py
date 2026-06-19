"""
crawl_report.py — Genera un reporte HTML a partir del JSON producido por crawl.py.

Uso:
    python crawl_report.py reports/www_cementospacasmayo_com_pe_urls.json
    python crawl_report.py reports/urls.json --spec specs/example_corporate.json
    python crawl_report.py reports/urls.json --out reports/mi_reporte.html
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click

# ─────────────────────────────────────────────────────────────────────────────
# Inferencia de tipo de página
# ─────────────────────────────────────────────────────────────────────────────

_TYPE_RULES: list[tuple[str, str, str]] = [
    (r"^/$",                                        "home",                 "Home"),
    (r"/contacto/formulario",                        "lead_form",            "Formulario Lead"),
    (r"/contacto/registrar",                         "lead_form",            "Formulario Registro"),
    (r"/contacto/denuncias",                         "lead_form",            "Formulario Denuncias"),
    (r"/contacto/mesa-de-partes",                    "lead_form",            "Mesa de Partes"),
    (r"/libro-de-reclamaciones",                     "lead_form",            "Libro Reclamaciones"),
    (r"/trabaja-con-nosotros",                       "lead_jobs",            "Formulario Empleo"),
    (r"/contacto",                                   "contact",              "Contacto"),
    (r"/productos.+/soluciones-categorias/.+/.+",    "product_detail",       "Ficha de Producto"),
    (r"/productos.+/soluciones-categorias",          "product_category",     "Categoría Producto"),
    (r"/productos.+/soluciones-tipo-obra",           "product_use_case",     "Soluciones por Obra"),
    (r"/productos.+/casos-aplicacion",               "product_use_case",     "Casos de Aplicación"),
    (r"/productos",                                  "product_listing",      "Listado Productos"),
    (r"/noticias/.+",                                "content_article",      "Artículo / Noticia"),
    (r"/noticias",                                   "content_listing",      "Listado Noticias"),
    (r"/eventos",                                    "content_listing",      "Eventos"),
    (r"/inversionistas",                             "institutional_inv",    "Inversionistas"),
    (r"/sostenibilidad",                             "institutional",        "Sostenibilidad"),
    (r"/innovacion",                                 "institutional",        "Innovación"),
    (r"/operaciones",                                "institutional",        "Operaciones"),
    (r"/nosotros",                                   "institutional",        "Nosotros"),
    (r"/terminos",                                   "legal",                "Legal / TyC"),
    (r"/politica",                                   "legal",                "Políticas"),
]

_TYPE_META: dict[str, dict[str, str]] = {
    "home":             {"color": "#3182ce", "bg": "#ebf8ff", "audit": "P1"},
    "lead_form":        {"color": "#805ad5", "bg": "#faf5ff", "audit": "P1"},
    "lead_jobs":        {"color": "#6b46c1", "bg": "#f3e8ff", "audit": "P2"},
    "contact":          {"color": "#9f7aea", "bg": "#faf5ff", "audit": "P2"},
    "product_detail":   {"color": "#38a169", "bg": "#f0fff4", "audit": "P1"},
    "product_category": {"color": "#2f855a", "bg": "#e6fffa", "audit": "P1"},
    "product_listing":  {"color": "#48bb78", "bg": "#f0fff4", "audit": "P2"},
    "product_use_case": {"color": "#276749", "bg": "#e6fffa", "audit": "P2"},
    "content_article":  {"color": "#dd6b20", "bg": "#fffaf0", "audit": "P2"},
    "content_listing":  {"color": "#c05621", "bg": "#fff5f5", "audit": "P3"},
    "institutional_inv":{"color": "#319795", "bg": "#e6fffa", "audit": "P2"},
    "institutional":    {"color": "#4299e1", "bg": "#ebf8ff", "audit": "P3"},
    "legal":            {"color": "#a0aec0", "bg": "#f7fafc", "audit": "P3"},
    "unknown":          {"color": "#718096", "bg": "#f7fafc", "audit": "P3"},
}


def _infer_type(pattern: str) -> tuple[str, str]:
    clean = pattern.replace("*/", "").rstrip("/")
    for regex, type_key, label in _TYPE_RULES:
        if re.search(regex, clean, re.IGNORECASE):
            return type_key, label
    return "unknown", "Sin clasificar"


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
:root{
  --bg:#f0f4f8;--card:#fff;--text:#1a202c;--muted:#718096;--border:#e2e8f0;
  --blue:#3182ce;--green:#38a169;--yellow:#d69e2e;--red:#e53e3e;
  --purple:#805ad5;--orange:#dd6b20;--teal:#319795;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 80px}

.hdr{background:linear-gradient(135deg,#1a202c 0%,#2d3748 100%);color:#fff;
     border-radius:12px;padding:32px;margin-bottom:20px}
.hdr .tool-tag{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;
     color:#a0aec0;font-weight:600;margin-bottom:6px}
.hdr h1{font-size:1.4rem;font-weight:700;color:#e2e8f0;margin-bottom:12px}
.hdr-meta{display:flex;flex-wrap:wrap;gap:12px 28px;font-size:.82rem;color:#a0aec0}
.hdr-meta strong{color:#e2e8f0}

.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
         gap:12px;margin-bottom:16px}
.kpi{background:var(--card);border-radius:10px;padding:20px 24px;
     box-shadow:0 1px 3px rgba(0,0,0,.08);border-left:4px solid var(--blue)}
.kpi-val{font-size:2rem;font-weight:800;color:#2d3748;line-height:1}
.kpi-lbl{font-size:.8rem;color:var(--muted);margin-top:4px}
.kpi.green{border-color:var(--green)}
.kpi.purple{border-color:var(--purple)}
.kpi.orange{border-color:var(--orange)}

.card{background:var(--card);border-radius:10px;padding:24px;
      margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card-title{font-size:.95rem;font-weight:700;color:#2d3748;
      padding-bottom:12px;margin-bottom:16px;border-bottom:2px solid var(--border)}

details.pattern-card{background:var(--card);border-radius:10px;
      margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
details.pattern-card>summary{
      padding:14px 20px;cursor:pointer;list-style:none;
      display:grid;grid-template-columns:1fr auto auto auto;
      align-items:center;gap:16px}
details.pattern-card>summary::-webkit-details-marker{display:none}
details.pattern-card[open]>summary{border-bottom:1px solid var(--border)}
details.pattern-card>summary::after{content:'\25BC';font-size:.7rem;
      color:var(--muted);transition:transform .2s;justify-self:end}
details.pattern-card[open]>summary::after{transform:rotate(180deg)}
.pat-body{padding:16px 20px 20px}

.type-badge{display:inline-block;padding:3px 10px;border-radius:999px;
     font-size:.73rem;font-weight:700;white-space:nowrap}
.audit-badge{display:inline-block;padding:2px 7px;border-radius:4px;
     font-size:.7rem;font-weight:700;text-transform:uppercase}
.audit-P1{background:#fed7d7;color:#742a2a}
.audit-P2{background:#fefcbf;color:#744210}
.audit-P3{background:#e2e8f0;color:#4a5568}

.pat-url{font-family:'Courier New',monospace;font-size:.8rem;font-weight:700;
     color:#2d3748;word-break:break-all}
.count-pill{background:#edf2f7;color:#4a5568;border-radius:999px;
     padding:2px 10px;font-size:.8rem;font-weight:700;white-space:nowrap}

.url-list{list-style:none;margin:0;padding:0}
.url-list li{padding:5px 0;border-bottom:1px solid #f7fafc;font-size:.8rem}
.url-list li:last-child{border-bottom:none}
.url-list a{color:var(--blue);text-decoration:none;word-break:break-all}
.url-list a:hover{text-decoration:underline}

.cmd-box{background:#1a202c;border-radius:6px;padding:10px 14px;
     font-family:'Courier New',monospace;font-size:.76rem;color:#a0aec0;
     white-space:pre-wrap;word-break:break-all;margin-top:10px;
     position:relative;cursor:pointer}
.cmd-box:hover{background:#2d3748}
.cmd-box .copy-hint{position:absolute;top:6px;right:10px;font-size:.68rem;
     color:#4a5568;font-family:sans-serif}

.warn{background:#fffbeb;border:1px solid #f6ad55;border-radius:8px;
     padding:14px 18px;margin-bottom:16px;font-size:.83rem;color:#744210}
.warn strong{color:#c05621}

.section-legend{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:.78rem;color:#4a5568}
.legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}

.footer{text-align:center;color:#cbd5e0;font-size:.76rem;padding:32px 0 8px}
@media(max-width:640px){.hdr{padding:20px}.kpi-row{grid-template-columns:1fr 1fr}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers HTML
# ─────────────────────────────────────────────────────────────────────────────

def _esc(v: object) -> str:
    return (
        str(v)
        .replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def _has_double_slash(urls: list[dict]) -> bool:
    return any("//" in urlparse(u["url"]).path for u in urls)


# ─────────────────────────────────────────────────────────────────────────────
# Secciones HTML
# ─────────────────────────────────────────────────────────────────────────────

def _sec_header(data: dict, now_fmt: str) -> str:
    domain   = data.get("domain", "")
    crawled  = data.get("discovered_at", "")
    source   = data.get("source", "")
    total    = data.get("total_urls", 0)
    return f"""
<div class="hdr">
  <div class="tool-tag">Tag Audit Tool &mdash; Crawl Report</div>
  <h1>{_esc(domain)}</h1>
  <div class="hdr-meta">
    <span><strong>URLs descubiertas:</strong> {total}</span>
    <span><strong>Fuente:</strong> {_esc(source)}</span>
    <span><strong>Crawleado:</strong> {_esc(crawled)}</span>
    <span><strong>Reporte generado:</strong> {_esc(now_fmt)}</span>
  </div>
</div>"""


def _sec_kpis(data: dict, patterns_with_type: list[dict]) -> str:
    total      = data.get("total_urls", 0)
    n_patterns = len(patterns_with_type)
    p1_count   = sum(1 for p in patterns_with_type if p["audit"] == "P1")

    type_counts: dict[str, int] = {}
    for p in patterns_with_type:
        type_counts[p["label"]] = type_counts.get(p["label"], 0) + p["count"]

    top = sorted(type_counts.items(), key=lambda x: -x[1])[:3]
    top_html = " &nbsp;·&nbsp; ".join(
        f"<strong>{_esc(lbl)}</strong> ({n})" for lbl, n in top
    )

    return f"""
<div class="kpi-row">
  <div class="kpi"><div class="kpi-val">{total}</div><div class="kpi-lbl">URLs descubiertas</div></div>
  <div class="kpi green"><div class="kpi-val">{n_patterns}</div><div class="kpi-lbl">Patrones de ruta</div></div>
  <div class="kpi purple"><div class="kpi-val">{p1_count}</div><div class="kpi-lbl">Patrones con prioridad P1</div></div>
  <div class="kpi orange" style="grid-column:span 1">
    <div class="kpi-lbl" style="margin-bottom:4px">Secciones principales</div>
    <div style="font-size:.82rem;color:#2d3748;font-weight:600">{top_html}</div>
  </div>
</div>"""


def _sec_warning(urls: list[dict]) -> str:
    if not _has_double_slash(urls):
        return ""
    return """
<div class="warn">
  <strong>Aviso:</strong> El sitemap del sitio genera URLs con doble barra <code>//</code>
  (ej. <code>https://dominio.com//contacto/</code>). La mayoría de servidores las toleran
  redirigiendo automáticamente, pero si alguna URL falla al auditar, elimina la barra doble
  antes del path.
</div>"""


def _sec_legend(patterns_with_type: list[dict]) -> str:
    seen: dict[str, str] = {}
    for p in patterns_with_type:
        if p["type"] not in seen:
            seen[p["type"]] = p["label"]

    items = "".join(
        f'<div class="legend-item">'
        f'<div class="legend-dot" style="background:{_TYPE_META.get(t, _TYPE_META["unknown"])["color"]}"></div>'
        f'{_esc(lbl)}</div>'
        for t, lbl in seen.items()
    )
    return f'<div class="section-legend">{items}</div>'


def _sec_patterns(patterns_with_type: list[dict], spec: str) -> str:
    cards: list[str] = []

    for p in patterns_with_type:
        meta    = _TYPE_META.get(p["type"], _TYPE_META["unknown"])
        color   = meta["color"]
        bg      = meta["bg"]
        audit   = p["audit"]
        label   = p["label"]
        pattern = p["pattern"]
        count   = p["count"]
        example = p["example"]
        urls    = p["urls"]

        type_badge = (
            f'<span class="type-badge" style="background:{bg};color:{color}">'
            f'{_esc(label)}</span>'
        )
        audit_badge = f'<span class="audit-badge audit-{audit}">{audit}</span>'
        count_pill  = f'<span class="count-pill">{count} URL{"s" if count > 1 else ""}</span>'

        # Lista de URLs
        url_items = "\n".join(
            f'<li><a href="{_esc(u)}" target="_blank">{_esc(u)}</a></li>'
            for u in urls
        )

        # Comando de auditoría
        cmd = f'python main.py --url "{example}" --spec {spec}'

        cards.append(f"""
<details class="pattern-card">
  <summary>
    <div>
      <div class="pat-url">{_esc(pattern)}</div>
      <div style="font-size:.75rem;color:var(--muted);margin-top:2px">
        Ej: <a href="{_esc(example)}" target="_blank"
               style="color:var(--blue);text-decoration:none">{_esc(example)}</a>
      </div>
    </div>
    {type_badge}
    {audit_badge}
    {count_pill}
  </summary>
  <div class="pat-body">
    <div style="margin-bottom:10px;font-size:.82rem;color:var(--muted)">
      Comando de auditoría recomendado (copia y ajusta la URL si hay varias):
    </div>
    <div class="cmd-box" onclick="navigator.clipboard.writeText(this.dataset.cmd)"
         data-cmd="{_esc(cmd)}" title="Clic para copiar">
      <span class="copy-hint">clic para copiar</span>{_esc(cmd)}
    </div>
    <details style="margin-top:14px">
      <summary style="font-size:.8rem;color:var(--blue);cursor:pointer;user-select:none">
        Ver las {count} URL{"s" if count > 1 else ""} de este patrón
      </summary>
      <ul class="url-list" style="margin-top:8px">{url_items}</ul>
    </details>
  </div>
</details>""")

    return f"""
<div class="card">
  <div class="card-title">Patrones de Ruta &mdash; {len(patterns_with_type)} grupos</div>
  {''.join(cards)}
</div>"""


def _sec_next_steps(domain: str, spec: str) -> str:
    return f"""
<div class="card">
  <div class="card-title">Siguientes Pasos</div>
  <ol style="padding-left:20px;line-height:2;font-size:.85rem;color:#4a5568">
    <li>Selecciona una URL representativa de cada patrón P1.</li>
    <li>Corre <code>main.py</code> con la URL y la spec elegida.</li>
    <li>Opcional: crea <code>urls_{domain.replace('.','_')}.txt</code> con las URLs
        elegidas y corre el buscador de oportunidades IA:<br>
        <code style="background:#f7fafc;padding:2px 6px;border-radius:3px">
          python site_main.py tag-plan --urls-file urls_{domain.replace('.','_')}.txt
        </code>
    </li>
  </ol>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Builder principal
# ─────────────────────────────────────────────────────────────────────────────

def build_report(data: dict, spec: str) -> str:
    now_fmt  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    domain   = data.get("domain", "sitio")
    patterns = data.get("patterns", [])
    urls     = data.get("urls", [])

    # Enriquecer patrones con tipo inferido
    patterns_with_type: list[dict] = []
    for p in patterns:
        type_key, label = _infer_type(p["pattern"])
        meta = _TYPE_META.get(type_key, _TYPE_META["unknown"])
        patterns_with_type.append({**p, "type": type_key, "label": label, "audit": meta["audit"]})

    # Ordenar: P1 primero, luego P2, luego por count desc
    order = {"P1": 0, "P2": 1, "P3": 2}
    patterns_with_type.sort(key=lambda x: (order[x["audit"]], -x["count"]))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Crawl Report &mdash; {_esc(domain)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_sec_header(data, now_fmt)}
{_sec_kpis(data, patterns_with_type)}
{_sec_warning(urls)}
{_sec_legend(patterns_with_type)}
{_sec_patterns(patterns_with_type, spec)}
{_sec_next_steps(domain, spec)}
<div class="footer">tag_auditor &mdash; Crawl Report &mdash; generado el {_esc(now_fmt)}</div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("json_path", metavar="CRAWL_JSON")
@click.option("--spec", default="specs/example_corporate.json", show_default=True,
              help="Spec a usar en los comandos de auditoría sugeridos")
@click.option("--out", default=None,
              help="Path del HTML de salida (default: mismo directorio que el JSON)")
def main(json_path: str, spec: str, out: str | None) -> None:
    """Genera un reporte HTML desde el JSON producido por crawl.py."""
    src = Path(json_path)
    if not src.exists():
        click.echo(f"\n  [ERROR] Archivo no encontrado: {src}", err=True)
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))

    if not data.get("patterns"):
        click.echo("\n  [ERROR] El JSON no contiene la clave 'patterns'.", err=True)
        click.echo("  Asegúrate de usar el JSON generado por crawl.py v2+.", err=True)
        sys.exit(1)

    html = build_report(data, spec)

    out_path = Path(out) if out else src.with_name(src.stem + "_report.html")
    out_path.write_text(html, encoding="utf-8")

    domain  = data.get("domain", "")
    n_pats  = len(data.get("patterns", []))
    n_urls  = data.get("total_urls", 0)
    click.echo(f"\n  Dominio  : {domain}")
    click.echo(f"  URLs     : {n_urls}   Patrones: {n_pats}")
    click.echo(f"  Reporte  : {out_path}\n")


if __name__ == "__main__":
    main()
