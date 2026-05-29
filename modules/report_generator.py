"""
M6 - Report Generator v2
Genera reports/{domain}_{timestamp}.html standalone y .json estructurado.
Secciones: header P1-score, IDs detectados, score bars por categoria,
validacion agrupada por categoria, brechas P1, dataLayer timeline, GA4 hits.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# CSS inline
# ──────────────────────────────────────────────────────────────────────────────
_CSS = """
:root{
  --bg:#f0f4f8;--card:#fff;--text:#1a202c;--muted:#718096;--border:#e2e8f0;
  --blue:#3182ce;--green:#38a169;--yellow:#d69e2e;--red:#e53e3e;
  --purple:#805ad5;--orange:#dd6b20;--teal:#319795;
  --cat-ecommerce:#3182ce;--cat-leads:#805ad5;--cat-custom:#dd6b20;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 80px}

/* HEADER */
.hdr{background:linear-gradient(135deg,#1a202c 0%,#2d3748 100%);color:#fff;
     border-radius:12px;padding:32px;margin-bottom:20px;
     display:flex;justify-content:space-between;align-items:flex-start;
     flex-wrap:wrap;gap:24px}
.hdr-left .tool-tag{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;
     color:#a0aec0;font-weight:600;margin-bottom:6px}
.hdr-left h1{font-size:1.3rem;font-weight:700;word-break:break-all;color:#e2e8f0;
     margin-bottom:8px}
.hdr-meta{display:flex;flex-wrap:wrap;gap:12px 24px;font-size:.82rem;color:#a0aec0}
.hdr-meta strong{color:#e2e8f0}
.p1-wrap{display:flex;flex-direction:column;align-items:center;gap:8px}
.p1-circle{width:96px;height:96px;border-radius:50%;border:4px solid;
     display:flex;flex-direction:column;align-items:center;
     justify-content:center;font-weight:700}
.p1-circle .num{font-size:1.9rem;line-height:1}
.p1-circle .lbl{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em}
.p1-detail{font-size:.8rem;color:#a0aec0;text-align:center}
.p1-detail strong{color:#e2e8f0}
.sc-green{border-color:#48bb78;color:#48bb78}
.sc-yellow{border-color:#ecc94b;color:#ecc94b}
.sc-red{border-color:#fc8181;color:#fc8181}

/* CARDS */
.card{background:var(--card);border-radius:10px;padding:24px;
      margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card-title{font-size:.95rem;font-weight:700;color:#2d3748;
      padding-bottom:12px;margin-bottom:16px;border-bottom:2px solid var(--border)}
details.card{padding:0}
details.card>summary{padding:20px 24px;cursor:pointer;list-style:none;
      display:flex;align-items:center;justify-content:space-between;
      border-bottom:2px solid transparent;border-radius:10px}
details.card>summary::-webkit-details-marker{display:none}
details.card[open]>summary{border-bottom-color:var(--border);border-radius:10px 10px 0 0}
details.card>summary .card-title{margin:0;padding:0;border:none}
details.card>summary::after{content:'\25BC';font-size:.75rem;color:var(--muted);
      transition:transform .2s}
details.card[open]>summary::after{transform:rotate(180deg)}
details.card>.card-body{padding:0 24px 24px}

/* CATEGORY SCORES */
.cat-scores{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.cat-card{padding:16px;border-radius:8px;border:1px solid var(--border)}
.cat-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.cat-name{font-weight:700;font-size:.85rem}
.cat-pct{font-size:.82rem;color:var(--muted)}
.bar-track{background:#edf2f7;border-radius:999px;height:8px;overflow:hidden;margin-bottom:6px}
.bar-fill{height:100%;border-radius:999px}
.cat-nums{font-size:.78rem;color:var(--muted)}
.cat-card.ecommerce .cat-name{color:var(--cat-ecommerce)}
.cat-card.ecommerce .bar-fill{background:var(--cat-ecommerce)}
.cat-card.leads     .cat-name{color:var(--cat-leads)}
.cat-card.leads     .bar-fill{background:var(--cat-leads)}
.cat-card.custom    .cat-name{color:var(--cat-custom)}
.cat-card.custom    .bar-fill{background:var(--cat-custom)}

/* IDs CHIPS */
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;
      font-size:.78rem;font-weight:600}
.chip-gtm{background:#ebf4ff;color:#2b6cb0}
.chip-ga4{background:#f0fff4;color:#276749}
.chip-meta{background:#e8f0fe;color:#1a56db}
.chip-hotjar{background:#fff5f5;color:#c53030}
.chip-clarity{background:#e6fffa;color:#285e61}
.chip-tiktok{background:#fce7f3;color:#9b2a9b}
.chip-linkedin{background:#dbeafe;color:#1d4ed8}
.chip-twitter{background:#e0f2fe;color:#0369a1}
.chip-google_ads{background:#fef3c7;color:#92400e}
.chip-none{background:#f7fafc;color:var(--muted);font-style:italic}

/* TABLES */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{background:#f7fafc;color:#4a5568;font-weight:600;padding:8px 12px;
   text-align:left;border-bottom:2px solid var(--border);white-space:nowrap}
td{padding:7px 12px;border-bottom:1px solid #edf2f7;vertical-align:top}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafafa}
.cat-row td{font-weight:700;font-size:.78rem;text-transform:uppercase;
     letter-spacing:.05em;padding:7px 12px}
.cat-row.ecommerce td{background:#ebf8ff;color:#2b6cb0}
.cat-row.leads     td{background:#faf5ff;color:#6b46c1}
.cat-row.custom    td{background:#fffaf0;color:#c05621}

/* BADGES */
.badge{display:inline-block;padding:2px 7px;border-radius:4px;
       font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.badge-completo{background:#c6f6d5;color:#22543d}
.badge-parcial{background:#fefcbf;color:#744210}
.badge-ausente{background:#fed7d7;color:#742a2a}
.badge-p1{background:#fed7d7;color:#742a2a}
.badge-p2{background:#fefcbf;color:#744210}
.badge-p3{background:#e2e8f0;color:#4a5568}

/* GAPS */
.gap-item{display:flex;gap:16px;padding:14px 0;border-bottom:1px solid var(--border)}
.gap-item:last-child{border-bottom:none}
.gap-badges{display:flex;flex-direction:column;gap:6px;min-width:90px}
.gap-body{flex:1}
.gap-name{font-weight:700;font-size:.92rem;color:#2d3748}
.gap-desc{color:var(--muted);font-size:.8rem;margin:2px 0 6px}
.gap-trigger{color:var(--muted);font-size:.76rem;font-style:italic;margin-bottom:6px}
.gap-missing{font-size:.8rem;color:var(--red)}
.gap-missing code{background:#fed7d7;padding:1px 5px;border-radius:3px;
     font-family:'Courier New',monospace;margin:0 2px}
.gap-typewr{font-size:.8rem;color:#d69e2e;margin-top:3px}
.gap-typewr code{background:#fefcbf;padding:1px 5px;border-radius:3px;
     font-family:'Courier New',monospace;margin:0 2px}

/* JSON collapsible */
details.json-d summary{color:#4299e1;font-size:.76rem;cursor:pointer;
     user-select:none;padding:2px 0}
details.json-d summary:hover{color:#2b6cb0}
.json-pre{background:#1a202c;color:#a0aec0;border-radius:6px;padding:10px 14px;
     font-family:'Courier New',monospace;font-size:.73rem;white-space:pre-wrap;
     word-break:break-all;max-height:200px;overflow-y:auto;margin-top:4px}

/* FOOTER */
.footer{text-align:center;color:#cbd5e0;font-size:.76rem;padding:32px 0 8px}

/* RESPONSIVE */
@media(max-width:640px){
  .hdr{padding:20px}.hdr h1{font-size:1.1rem}.card{padding:16px}
  .cat-scores{grid-template-columns:1fr}
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _esc(v: Any) -> str:
    return (
        str(v)
        .replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def _json_collapse(obj: Any, summary: str = "Ver parametros") -> str:
    try:
        body = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        body = str(obj)
    return (
        f'<details class="json-d"><summary>{_esc(summary)}</summary>'
        f'<pre class="json-pre">{_esc(body)}</pre></details>'
    )


def _ts(ms: int | None) -> str:
    if not ms:
        return "-"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(ms)


def _score_cls(pct: float) -> str:
    return "sc-green" if pct >= 80 else ("sc-yellow" if pct >= 50 else "sc-red")


def _badge(label: str, kind: str) -> str:
    cls = {
        "COMPLETO": "badge-completo", "PARCIAL": "badge-parcial",
        "AUSENTE": "badge-ausente",
        "P1": "badge-p1", "P2": "badge-p2", "P3": "badge-p3",
    }.get(label, "badge-p3")
    return f'<span class="badge {cls}">{_esc(label)}</span>'


def _chip(label: str, kind: str) -> str:
    cls = f"chip-{kind}" if kind in (
        "gtm", "ga4", "meta", "hotjar", "clarity", "tiktok",
        "linkedin", "twitter", "google_ads"
    ) else "chip-ga4"
    return f'<span class="chip {cls}">{_esc(label)}</span>'


# ──────────────────────────────────────────────────────────────────────────────
# Section builders
# ──────────────────────────────────────────────────────────────────────────────

def _sec_header(
    url: str, client: str, spec_meta: dict, scores: dict, now_fmt: str
) -> str:
    p1  = scores.get("p1", {})
    pct = p1.get("pct", 0.0)
    ok  = p1.get("ok", 0)
    tot = p1.get("total", 0)
    cls = _score_cls(pct)

    site    = spec_meta.get("site", "")
    version = spec_meta.get("version", "1.0")
    spec_fn = spec_meta.get("_filename", "")

    return f"""
<div class="hdr">
  <div class="hdr-left">
    <div class="tool-tag">Tag Audit Report v2.0</div>
    <h1>{_esc(url)}</h1>
    <div class="hdr-meta">
      <span><strong>Cliente:</strong> {_esc(client or site or '-')}</span>
      <span><strong>Spec:</strong> {_esc(spec_fn)} v{_esc(version)}</span>
      <span><strong>Fecha:</strong> {_esc(now_fmt)}</span>
    </div>
  </div>
  <div class="p1-wrap">
    <div class="p1-circle {cls}">
      <span class="num">{pct:.0f}%</span>
      <span class="lbl">Score P1</span>
    </div>
    <div class="p1-detail"><strong>{ok}/{tot}</strong> eventos criticos OK</div>
  </div>
</div>"""


def _sec_ids(gtm_info: dict, ga4_from_hits: list[str], pixels: list[str], tp: dict) -> str:
    gtm_ids = gtm_info.get("gtm_ids", [])
    ga4_ids = sorted({*gtm_info.get("ga4_ids", []), *ga4_from_hits})

    gtm_html = " ".join(_chip(i, "gtm") for i in gtm_ids) or '<span class="chip chip-none">No detectado</span>'
    ga4_html = " ".join(_chip(i, "ga4") for i in ga4_ids) or '<span class="chip chip-none">No detectado</span>'
    px_html  = " ".join(_chip(p, p) for p in pixels)      or '<span class="chip chip-none">Ninguno</span>'

    # Terceros detectados en runtime
    tp_items = [(k.replace("_", " ").title(), v) for k, v in (tp or {}).items()]
    tp_rows  = "\n".join(
        f"<tr><td>{_esc(k)}</td>"
        f"<td>{'<span style=\"color:#38a169;font-weight:600\">Detectado</span>' if v else '<span style=\"color:#718096\">No detectado</span>'}</td></tr>"
        for k, v in tp_items
    ) if tp_items else ""

    tp_section = f"""
<table style="margin-top:12px">
  <tr><th>Script de tercero</th><th>Estado runtime</th></tr>
  {tp_rows}
</table>""" if tp_rows else ""

    return f"""
<div class="card">
  <div class="card-title">IDs y Scripts de Tracking Detectados</div>
  <table>
    <tr><th style="width:170px">Tipo</th><th>Identificadores</th></tr>
    <tr><td>GTM Container</td><td><div class="chips">{gtm_html}</div></td></tr>
    <tr><td>GA4 Measurement ID</td><td><div class="chips">{ga4_html}</div></td></tr>
    <tr><td>Pixels (network)</td><td><div class="chips">{px_html}</div></td></tr>
  </table>
  {tp_section}
</div>"""


def _sec_cat_scores(scores: dict) -> str:
    cats = [
        ("ecommerce", "E-commerce"),
        ("leads",     "Leads"),
        ("custom",    "Custom"),
    ]
    cards = []
    for key, label in cats:
        s = scores.get(key, {"ok": 0, "total": 0, "pct": 0.0})
        if s["total"] == 0:
            continue
        cards.append(f"""
<div class="cat-card {key}">
  <div class="cat-card-header">
    <span class="cat-name">{label}</span>
    <span class="cat-pct">{s['pct']:.0f}%</span>
  </div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{s['pct']:.0f}%"></div>
  </div>
  <div class="cat-nums">{s['ok']} de {s['total']} eventos COMPLETO</div>
</div>""")

    if not cards:
        return ""
    return f"""
<div class="card">
  <div class="card-title">Cobertura por Categoria</div>
  <div class="cat-scores">{''.join(cards)}</div>
</div>"""


def _sec_validation(results: list[dict]) -> str:
    cat_order = [("ecommerce", "E-commerce"), ("leads", "Leads"), ("custom", "Custom")]
    prio_order = {"P1": 0, "P2": 1, "P3": 2}

    all_rows: list[str] = []
    for cat_key, cat_label in cat_order:
        evs = sorted(
            [r for r in results if r["category"] == cat_key],
            key=lambda r: (prio_order.get(r["priority"], 9), r["event_name"]),
        )
        if not evs:
            continue
        ok_n = sum(1 for e in evs if e["status"] == "COMPLETO")
        all_rows.append(
            f'<tr class="cat-row {cat_key}"><td colspan="6">'
            f'{cat_label} &mdash; {ok_n}/{len(evs)} COMPLETO</td></tr>'
        )
        for r in evs:
            found_html   = " ".join(f'<code style="font-size:.75rem">{_esc(p)}</code>' for p in r["found_params"])   or "&mdash;"
            missing_html = " ".join(f'<code style="font-size:.75rem;color:#c53030">{_esc(p)}</code>' for p in r["missing_params"]) or "&mdash;"
            tw_html      = " ".join(f'<code style="font-size:.75rem;color:#d69e2e">{_esc(p)}</code>' for p in r.get("type_errors", [])) or ""
            if tw_html:
                missing_html += f"<br><span style='font-size:.74rem;color:#d69e2e'>tipo incorrecto: {tw_html}</span>"
            all_rows.append(f"""<tr>
  <td><strong>{_esc(r['event_name'])}</strong>
    <div style="color:var(--muted);font-size:.76rem">{_esc(r.get('description',''))}</div></td>
  <td>{_badge(r['priority'], r['priority'])}</td>
  <td>{_badge(r['status'], r['status'])}</td>
  <td style="font-size:.78rem">{found_html}</td>
  <td style="font-size:.78rem">{missing_html}</td>
  <td style="color:var(--muted)">{r['instances_count']}</td>
</tr>""")

    return f"""
<div class="card">
  <div class="card-title">Validacion contra Spec</div>
  <div class="tbl-wrap">
    <table>
      <tr><th>Evento</th><th>Prio.</th><th>Estado</th>
          <th>Params OK</th><th>Params faltantes / tipo</th><th>Inst.</th></tr>
      {''.join(all_rows)}
    </table>
  </div>
</div>"""


def _sec_p1_gaps(gaps: list[dict]) -> str:
    p1_gaps = [g for g in gaps if g["priority"] == "P1"]
    if not p1_gaps:
        return """
<div class="card">
  <div class="card-title">Brechas P1 - Eventos Criticos</div>
  <p style="color:#38a169;font-weight:600;padding:8px 0">
    Sin brechas P1 &mdash; todos los eventos criticos estan COMPLETO.</p>
</div>"""

    items = []
    for g in p1_gaps:
        miss_html = "".join(f"<code>{_esc(p)}</code>" for p in g["missing_params"]) or "(evento no disparado)"
        tw_html   = "".join(f"<code>{_esc(p)}</code>" for p in g.get("type_errors", []))
        tw_block  = f'<div class="gap-typewr">Tipo incorrecto: {tw_html}</div>' if tw_html else ""
        items.append(f"""
<div class="gap-item">
  <div class="gap-badges">
    {_badge(g['priority'], g['priority'])}
    {_badge(g['status'], g['status'])}
    <span style="font-size:.74rem;color:var(--muted)">{_esc(g.get('category',''))}</span>
  </div>
  <div class="gap-body">
    <div class="gap-name">{_esc(g['event_name'])}</div>
    <div class="gap-desc">{_esc(g.get('description',''))}</div>
    <div class="gap-trigger">Trigger: {_esc(g.get('trigger',''))}</div>
    <div class="gap-missing">Params faltantes: {miss_html}</div>
    {tw_block}
  </div>
</div>""")

    return f"""
<div class="card">
  <div class="card-title">Brechas P1 &mdash; Eventos Criticos ({len(p1_gaps)})</div>
  {''.join(items)}
</div>"""


def _sec_datalayer(events: list[dict]) -> str:
    if not events:
        rows = "<tr><td colspan='4' style='text-align:center;color:var(--muted)'>Sin eventos capturados</td></tr>"
    else:
        rows_list = []
        for ev in events:
            data   = ev.get("payload", {})
            name   = data.get("event", "&mdash;")
            params = {k: v for k, v in data.items() if k != "event"}
            rows_list.append(
                f"<tr><td>{ev.get('index','')}</td><td>{_ts(ev.get('ts'))}</td>"
                f"<td><strong>{_esc(name)}</strong></td>"
                f"<td>{_json_collapse(params) if params else '&mdash;'}</td></tr>"
            )
        rows = "\n".join(rows_list)

    return f"""
<details class="card">
  <summary><div class="card-title">dataLayer Timeline &mdash; {len(events)} eventos capturados</div></summary>
  <div class="card-body">
    <div class="tbl-wrap">
      <table>
        <tr><th>#</th><th>Hora</th><th>Evento</th><th>Payload</th></tr>
        {rows}
      </table>
    </div>
  </div>
</details>"""


def _sec_ga4_hits(hits: list[dict]) -> str:
    if not hits:
        rows = "<tr><td colspan='4' style='text-align:center;color:var(--muted)'>Sin hits interceptados</td></tr>"
    else:
        rows_list = []
        for h in hits:
            rows_list.append(
                f"<tr><td>{_ts(h.get('timestamp'))}</td>"
                f"<td><strong>{_esc(h.get('event_name',''))}</strong></td>"
                f"<td>{_esc(h.get('measurement_id',''))}</td>"
                f"<td>{_json_collapse(h.get('event_params',{})) if h.get('event_params') else '&mdash;'}</td></tr>"
            )
        rows = "\n".join(rows_list)

    return f"""
<details class="card">
  <summary><div class="card-title">GA4 Hits Interceptados &mdash; {len(hits)} hits</div></summary>
  <div class="card-body">
    <div class="tbl-wrap">
      <table>
        <tr><th>Hora</th><th>Evento</th><th>Measurement ID</th><th>Event Params</th></tr>
        {rows}
      </table>
    </div>
  </div>
</details>"""


# ──────────────────────────────────────────────────────────────────────────────
# ReportGenerator
# ──────────────────────────────────────────────────────────────────────────────

class ReportGenerator:
    def __init__(self, output_dir: str = "reports") -> None:
        self._out = Path(output_dir)
        self._out.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(url: str) -> str:
        domain = re.sub(r"https?://", "", url).split("/")[0]
        return re.sub(r"[^\w]", "_", domain)[:50]

    def generate(
        self,
        url: str,
        spec_meta: dict[str, Any],
        gtm_info: dict[str, Any],
        ga4_hits: list[dict[str, Any]],
        pixel_types: list[str],
        dl_events: list[dict[str, Any]],
        validation: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> tuple[Path, Path]:
        domain   = self._safe_name(url)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        now_fmt  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base     = self._out / f"{domain}_{ts}"

        client       = spec_meta.get("client", spec_meta.get("site", ""))
        scores       = validation.get("scores", {})
        results      = validation.get("results", [])
        gaps         = validation.get("gaps", [])
        ga4_ids_hits = sorted({h["measurement_id"] for h in ga4_hits if h.get("measurement_id")})
        tp           = gtm_info.get("third_party", {})

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tag Audit &mdash; {_esc(domain)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_sec_header(url, client, spec_meta, scores, now_fmt)}
{_sec_ids(gtm_info, ga4_ids_hits, pixel_types, tp)}
{_sec_cat_scores(scores)}
{_sec_validation(results)}
{_sec_p1_gaps(gaps)}
{_sec_datalayer(dl_events)}
{_sec_ga4_hits(ga4_hits)}
<div class="footer">tag_auditor v2.0 &mdash; generado el {_esc(now_fmt)}</div>
</div>
</body>
</html>"""

        html_path = Path(str(base) + ".html")
        html_path.write_text(html, encoding="utf-8")

        data: dict[str, Any] = {
            "meta": {"url": url, "generated_at": now_fmt},
            "spec": spec_meta,
            "gtm_info": gtm_info,
            "ga4_measurement_ids": ga4_ids_hits,
            "detected_pixels": pixel_types,
            "ga4_hits": ga4_hits,
            "datalayer_events": dl_events,
            "validation": validation,
            "interactions": actions,
        }
        json_path = Path(str(base) + ".json")
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        return html_path, json_path
