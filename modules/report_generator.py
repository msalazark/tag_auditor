"""
M6 - Report Generator
Genera reports/{domain}_{timestamp}.html (standalone, sin dependencias externas)
y reports/{domain}_{timestamp}.json con toda la data estructurada.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# CSS inline para el reporte HTML standalone
# ──────────────────────────────────────────────────────────────────────────────
_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f7fa; color: #1a1a2e; line-height: 1.5; }
.wrap { max-width: 1280px; margin: 0 auto; padding: 24px 16px 64px; }

/* Header */
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
          color: #fff; border-radius: 12px; padding: 32px 36px; margin-bottom: 24px; }
.header h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 6px; }
.header .meta { font-size: 0.85rem; color: #a0aec0; }
.header .url { font-size: 0.95rem; color: #63b3ed; word-break: break-all; margin: 6px 0; }

/* Score badge */
.score-wrap { display: flex; align-items: center; gap: 20px; margin-top: 18px; flex-wrap: wrap; }
.score-badge { width: 90px; height: 90px; border-radius: 50%;
               display: flex; flex-direction: column; align-items: center;
               justify-content: center; font-weight: 700; border: 4px solid; }
.score-num { font-size: 1.8rem; }
.score-lbl { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px; }
.score-green  { border-color: #48bb78; color: #48bb78; }
.score-yellow { border-color: #ecc94b; color: #ecc94b; }
.score-red    { border-color: #fc8181; color: #fc8181; }
.score-meta p { color: #cbd5e0; font-size: 0.9rem; }
.score-meta strong { color: #fff; }

/* Sections */
.section { background: #fff; border-radius: 10px; padding: 24px 28px;
           margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.07); }
.section h2 { font-size: 1.05rem; font-weight: 700; margin-bottom: 16px;
              padding-bottom: 10px; border-bottom: 2px solid #e2e8f0; color: #2d3748; }

/* ID chips */
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px;
        border-radius: 20px; font-size: 0.82rem; font-weight: 600; }
.chip-gtm  { background: #ebf4ff; color: #2b6cb0; }
.chip-ga4  { background: #f0fff4; color: #276749; }
.chip-meta { background: #e8f0fe; color: #1a56db; }
.chip-tiktok { background: #fce7f3; color: #9b2a9b; }
.chip-linkedin { background: #dbeafe; color: #1d4ed8; }
.chip-twitter  { background: #e0f2fe; color: #0369a1; }
.chip-google_ads { background: #fef3c7; color: #92400e; }
.chip-none { background: #f7fafc; color: #718096; font-style: italic; }

/* Tables */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
th { background: #f7fafc; text-align: left; padding: 9px 12px; font-weight: 600;
     color: #4a5568; border-bottom: 2px solid #e2e8f0; white-space: nowrap; }
td { padding: 8px 12px; border-bottom: 1px solid #edf2f7; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f7fafc; }

/* Status badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
.badge-ok      { background: #c6f6d5; color: #22543d; }
.badge-parcial { background: #fefcbf; color: #744210; }
.badge-ausente { background: #fed7d7; color: #742a2a; }
.badge-p1 { background: #fed7d7; color: #742a2a; }
.badge-p2 { background: #fefcbf; color: #744210; }
.badge-p3 { background: #e2e8f0; color: #4a5568; }

/* Collapsible JSON */
details { margin-top: 2px; }
details summary { cursor: pointer; color: #4299e1; font-size: 0.78rem;
                  user-select: none; padding: 2px 0; }
details summary:hover { color: #2b6cb0; }
.json-block { background: #1a202c; color: #a0aec0; border-radius: 6px;
              padding: 10px 14px; font-family: 'Fira Code', 'Courier New', monospace;
              font-size: 0.75rem; white-space: pre-wrap; word-break: break-all;
              max-height: 300px; overflow-y: auto; margin-top: 6px; }

/* Gaps list */
.gap-item { display: flex; align-items: flex-start; gap: 12px;
            padding: 12px 0; border-bottom: 1px solid #edf2f7; }
.gap-item:last-child { border-bottom: none; }
.gap-left { min-width: 120px; }
.gap-right { flex: 1; }
.gap-right .ev-name { font-weight: 700; font-size: 0.92rem; }
.gap-right .ev-miss { color: #e53e3e; font-size: 0.82rem; margin-top: 3px; }
.gap-right .ev-found { color: #38a169; font-size: 0.82rem; }

/* Responsive */
@media (max-width: 640px) {
  .header { padding: 20px; }
  .section { padding: 16px; }
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escapar HTML básico."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _json_block(obj: Any) -> str:
    try:
        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        pretty = str(obj)
    return (
        "<details><summary>Ver parámetros</summary>"
        f'<pre class="json-block">{_esc(pretty)}</pre>'
        "</details>"
    )


def _ts_fmt(ts_ms: int | None) -> str:
    if not ts_ms:
        return "—"
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(ts_ms)


def _score_class(score: float) -> str:
    if score >= 80:
        return "score-green"
    if score >= 50:
        return "score-yellow"
    return "score-red"


def _chip(label: str, kind: str) -> str:
    css = f"chip-{kind}" if kind in (
        "gtm", "ga4", "meta", "tiktok", "linkedin", "twitter", "google_ads"
    ) else "chip-ga4"
    return f'<span class="chip {css}">{_esc(label)}</span>'


def _badge_status(status: str) -> str:
    cls = {"OK": "badge-ok", "PARCIAL": "badge-parcial", "AUSENTE": "badge-ausente"}.get(
        status, "badge-ausente"
    )
    return f'<span class="badge {cls}">{_esc(status)}</span>'


def _badge_priority(priority: str) -> str:
    cls = {"P1": "badge-p1", "P2": "badge-p2", "P3": "badge-p3"}.get(priority, "badge-p3")
    return f'<span class="badge {cls}">{_esc(priority)}</span>'


# ──────────────────────────────────────────────────────────────────────────────
# HTML section builders
# ──────────────────────────────────────────────────────────────────────────────

def _section_ids(gtm_info: dict, ga4_ids_from_hits: list[str], pixels: list[str]) -> str:
    gtm_ids = gtm_info.get("gtm_ids", [])
    ga4_ids = list({*gtm_info.get("ga4_ids", []), *ga4_ids_from_hits})

    gtm_html = " ".join(_chip(i, "gtm") for i in gtm_ids) or '<span class="chip chip-none">No detectado</span>'
    ga4_html = " ".join(_chip(i, "ga4") for i in ga4_ids) or '<span class="chip chip-none">No detectado</span>'
    px_html = " ".join(_chip(p, p) for p in pixels) or '<span class="chip chip-none">Ninguno detectado</span>'

    return f"""
<div class="section">
  <h2>IDs de Tracking Detectados</h2>
  <table>
    <tr><th style="width:160px">Tipo</th><th>Identificadores</th></tr>
    <tr><td>GTM Container</td><td><div class="chips">{gtm_html}</div></td></tr>
    <tr><td>GA4 Measurement ID</td><td><div class="chips">{ga4_html}</div></td></tr>
    <tr><td>Otros pixels</td><td><div class="chips">{px_html}</div></td></tr>
  </table>
</div>"""


def _section_datalayer(events: list[dict]) -> str:
    if not events:
        rows = "<tr><td colspan='4' style='color:#718096;text-align:center'>Sin eventos capturados</td></tr>"
    else:
        rows_list = []
        for ev in events:
            idx = ev.get("index", "")
            ts = _ts_fmt(ev.get("timestamp"))
            data = ev.get("data", {})
            name = _esc(data.get("event", "—"))
            params = {k: v for k, v in data.items() if k != "event"}
            rows_list.append(
                f"<tr><td>{idx}</td><td>{ts}</td>"
                f"<td><strong>{name}</strong></td>"
                f"<td>{_json_block(params) if params else '—'}</td></tr>"
            )
        rows = "\n".join(rows_list)

    return f"""
<div class="section">
  <h2>dataLayer Timeline ({len(events)} eventos)</h2>
  <div class="tbl-wrap">
    <table>
      <tr><th>#</th><th>Hora</th><th>Evento</th><th>Parámetros</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _section_ga4_hits(hits: list[dict]) -> str:
    if not hits:
        rows = "<tr><td colspan='4' style='color:#718096;text-align:center'>Sin hits capturados</td></tr>"
    else:
        rows_list = []
        for h in hits:
            ts = _ts_fmt(h.get("timestamp"))
            name = _esc(h.get("event_name", "—"))
            mid = _esc(h.get("measurement_id", "—"))
            params = h.get("event_params", {})
            rows_list.append(
                f"<tr><td>{ts}</td><td><strong>{name}</strong></td>"
                f"<td>{mid}</td>"
                f"<td>{_json_block(params) if params else '—'}</td></tr>"
            )
        rows = "\n".join(rows_list)

    return f"""
<div class="section">
  <h2>Hits GA4 Interceptados ({len(hits)} hits)</h2>
  <div class="tbl-wrap">
    <table>
      <tr><th>Hora</th><th>Evento</th><th>Measurement ID</th><th>Parámetros</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _section_spec(validation: dict) -> str:
    results = validation.get("results", [])
    if not results:
        rows = "<tr><td colspan='5' style='color:#718096;text-align:center'>Sin spec cargada</td></tr>"
    else:
        rows_list = []
        for r in results:
            found = ", ".join(r.get("found_params", [])) or "—"
            missing = ", ".join(r.get("missing_params", [])) or "—"
            rows_list.append(
                f"<tr>"
                f"<td><strong>{_esc(r['event_name'])}</strong></td>"
                f"<td>{_badge_priority(r['priority'])}</td>"
                f"<td>{_badge_status(r['status'])}</td>"
                f"<td style='color:#38a169'>{_esc(found)}</td>"
                f"<td style='color:#e53e3e'>{_esc(missing)}</td>"
                f"</tr>"
            )
        rows = "\n".join(rows_list)

    return f"""
<div class="section">
  <h2>Validación contra Spec ({validation.get('ok_count',0)}/{validation.get('total_count',0)} OK)</h2>
  <div class="tbl-wrap">
    <table>
      <tr><th>Evento</th><th>Prioridad</th><th>Estado</th><th>Params encontrados</th><th>Params faltantes</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _section_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return """
<div class="section">
  <h2>Brechas Detectadas</h2>
  <p style="color:#38a169;font-weight:600">Sin brechas — todos los eventos cumplen la spec ✓</p>
</div>"""

    items = []
    for g in gaps:
        missing_str = ", ".join(g.get("missing_params", [])) or "Evento no disparado"
        found_str = ", ".join(g.get("found_params", [])) or "Ninguno"
        items.append(f"""
<div class="gap-item">
  <div class="gap-left">
    {_badge_priority(g['priority'])}
    <br><br>
    {_badge_status(g['status'])}
  </div>
  <div class="gap-right">
    <div class="ev-name">{_esc(g['event_name'])}</div>
    <div style="color:#718096;font-size:.8rem">Trigger: {_esc(g.get('trigger','—'))}</div>
    <div class="ev-miss">Params faltantes: {_esc(missing_str)}</div>
    <div class="ev-found">Params encontrados: {_esc(found_str)}</div>
  </div>
</div>""")

    return f"""
<div class="section">
  <h2>Brechas Detectadas ({len(gaps)})</h2>
  {''.join(items)}
</div>"""


# ──────────────────────────────────────────────────────────────────────────────
# ReportGenerator
# ──────────────────────────────────────────────────────────────────────────────

class ReportGenerator:
    def __init__(self, output_dir: str = "reports") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_domain(url: str) -> str:
        domain = re.sub(r"https?://", "", url).split("/")[0]
        return re.sub(r"[^\w\-.]", "_", domain)[:60]

    def generate(
        self,
        url: str,
        gtm_info: dict[str, Any],
        ga4_hits: list[dict[str, Any]],
        pixel_types: list[str],
        datalayer_events: list[dict[str, Any]],
        validation: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> tuple[Path, Path]:
        """
        Escribe HTML + JSON y retorna (html_path, json_path).
        """
        domain = self._safe_domain(url)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self._output_dir / f"{domain}_{ts}"

        ga4_ids_from_hits = list({h["measurement_id"] for h in ga4_hits if h.get("measurement_id")})
        score = validation.get("coverage_score", 0.0)
        ok = validation.get("ok_count", 0)
        total = validation.get("total_count", 0)
        gaps = validation.get("gaps", [])

        # ── HTML ──────────────────────────────────────────────────────────────
        score_cls = _score_class(score)
        now_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tag Audit — {_esc(domain)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

<!-- HEADER -->
<div class="header">
  <h1>Tag Audit Report</h1>
  <div class="url">{_esc(url)}</div>
  <div class="meta">Generado el {now_fmt}</div>
  <div class="score-wrap">
    <div class="score-badge {score_cls}">
      <span class="score-num">{score:.0f}</span>
      <span class="score-lbl">Score</span>
    </div>
    <div class="score-meta">
      <p><strong>{ok} / {total}</strong> eventos en spec con estado OK</p>
      <p>{len(ga4_hits)} hits GA4 · {len(datalayer_events)} pushes dataLayer</p>
      <p>{len(gaps)} brechas detectadas</p>
    </div>
  </div>
</div>

{_section_ids(gtm_info, ga4_ids_from_hits, pixel_types)}
{_section_spec(validation)}
{_section_gaps(gaps)}
{_section_datalayer(datalayer_events)}
{_section_ga4_hits(ga4_hits)}

</div>
</body>
</html>"""

        # Usar concatenación directa para evitar que Path.with_suffix
        # trunque dominios con múltiples puntos (ej. .com.pe)
        html_path = Path(str(base) + ".html")
        html_path.write_text(html, encoding="utf-8")

        # ── JSON ──────────────────────────────────────────────────────────────
        data: dict[str, Any] = {
            "meta": {
                "url": url,
                "generated_at": now_fmt,
                "coverage_score": score,
            },
            "gtm_info": gtm_info,
            "ga4_measurement_ids": ga4_ids_from_hits,
            "detected_pixels": pixel_types,
            "ga4_hits": ga4_hits,
            "datalayer_events": datalayer_events,
            "validation": validation,
            "interactions": actions,
        }

        json_path = Path(str(base) + ".json")
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        return html_path, json_path
