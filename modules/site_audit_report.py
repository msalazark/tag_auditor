"""
Generador de reportes HTML para auditorías site-wide (site_audit_results.json).
Lee el output del crawler multi-página y produce un HTML standalone.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.report_generator import (
    _CSS,
    _esc,
    _ts,
    _sec_ids,
    _sec_datalayer,
    _sec_ga4_hits,
)


# ──────────────────────────────────────────────────────────────────────────────
# Agregación de datos cross-journey
# ──────────────────────────────────────────────────────────────────────────────

def _aggregate(data: dict) -> dict:
    """Consolida GTM IDs, GA4, pixels y eventos desde todos los steps."""
    gtm_ids: set[str] = set()
    ga4_ids: set[str] = set()
    pixels: set[str] = set()
    third_party: dict[str, bool] = {}
    all_dl: list[dict] = []
    all_ga4: list[dict] = []

    for journey in data.get("journeys", []):
        jname = journey.get("journey_name", journey.get("journey_id", ""))
        for step in journey.get("steps", []):
            gtm = step.get("gtm_info", {})
            for gid in gtm.get("gtm_ids", []):
                gtm_ids.add(gid)
            for gid in gtm.get("ga4_ids", []):
                ga4_ids.add(gid)
            for k, v in gtm.get("third_party", {}).items():
                if v:
                    third_party[k] = True
                    pixels.add(k)
            for ev in step.get("new_datalayer_events", []):
                all_dl.append({**ev, "_url": step.get("url", ""), "_journey": jname})

        for hit in journey.get("ga4_hits", []):
            all_ga4.append(hit)

    return {
        "gtm_ids": sorted(gtm_ids),
        "ga4_ids": sorted(ga4_ids),
        "pixels": sorted(pixels),
        "third_party": third_party,
        "all_dl": all_dl,
        "all_ga4": all_ga4,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de render
# ──────────────────────────────────────────────────────────────────────────────

def _stat(n: int | str, label: str) -> str:
    return (
        f'<div style="text-align:center;background:rgba(255,255,255,.12);'
        f'border-radius:8px;padding:10px 16px;min-width:72px">'
        f'<div style="font-size:1.6rem;font-weight:700;color:#e2e8f0">{n}</div>'
        f'<div style="font-size:.68rem;color:#a0aec0;text-transform:uppercase;'
        f'letter-spacing:.1em">{_esc(label)}</div></div>'
    )


def _finding(kind: str, msg: str) -> str:
    icons = {"ok": "✅", "warn": "⚠️", "critical": "🔴", "info": "ℹ️"}
    bg    = {"ok": "#f0fff4", "warn": "#fffff0", "critical": "#fff5f5", "info": "#ebf8ff"}
    fg    = {"ok": "#22543d", "warn": "#744210", "critical": "#742a2a", "info": "#2a4365"}
    return (
        f'<div style="padding:10px 16px;border-radius:6px;margin-bottom:8px;'
        f'background:{bg[kind]};color:{fg[kind]};font-size:.88rem;line-height:1.6">'
        f'{icons[kind]} {_esc(msg)}</div>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Secciones HTML
# ──────────────────────────────────────────────────────────────────────────────

def _sec_header(data: dict, agg: dict) -> str:
    domain  = data.get("domain", "")
    disc_at = data.get("discovered_at", "")[:19].replace("T", " ")
    journeys = data.get("journeys", [])
    steps    = sum(len(j.get("steps", [])) for j in journeys)
    return f"""
<div class="hdr">
  <div class="hdr-left">
    <div class="tool-tag">Tag Audit Report &mdash; Site-Wide / Crawler</div>
    <h1>{_esc(domain)}</h1>
    <div class="hdr-meta">
      <span><strong>Descubierto:</strong> {_esc(disc_at)}</span>
      <span><strong>Journeys:</strong> {len(journeys)}</span>
      <span><strong>URLs auditadas:</strong> {steps}</span>
    </div>
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    {_stat(steps,              "URLs")}
    {_stat(len(agg["all_dl"]), "dataLayer")}
    {_stat(len(agg["all_ga4"]),"GA4 hits")}
    {_stat(len(agg["gtm_ids"]),"GTM IDs")}
  </div>
</div>"""


def _sec_findings(data: dict, agg: dict) -> str:
    tp = agg["third_party"]
    journeys = data.get("journeys", [])
    total_urls = sum(len(j.get("steps", [])) for j in journeys)

    parts: list[str] = []

    # GTM
    for gid in agg["gtm_ids"]:
        parts.append(_finding("ok", f"GTM activo: {gid}"))
    if not agg["gtm_ids"]:
        parts.append(_finding("critical", "GTM no detectado en ninguna pagina auditada"))

    # GA4
    for gid in agg["ga4_ids"]:
        parts.append(_finding("ok", f"GA4 configurado: {gid}"))
    if not agg["ga4_ids"]:
        parts.append(_finding("critical", "GA4 no detectado"))

    # Pixels
    if tp.get("meta_pixel"):   parts.append(_finding("ok",   "Meta Pixel activo"))
    if tp.get("google_ads"):   parts.append(_finding("ok",   "Google Ads detectado"))
    if tp.get("hotjar"):       parts.append(_finding("info", "Hotjar detectado"))
    if tp.get("clarity"):      parts.append(_finding("info", "Microsoft Clarity detectado"))
    if tp.get("tiktok"):       parts.append(_finding("info", "TikTok Pixel detectado"))
    if tp.get("linkedin"):     parts.append(_finding("info", "LinkedIn Insight Tag detectado"))

    # Consent Mode
    consent_evs = [
        e for e in agg["all_dl"]
        if e.get("payload", {}).get("0") == "consent"
        or "consent" in str(e.get("payload", {}).get("event", "")).lower()
    ]
    if consent_evs:
        has_denied = any("denied" in str(e.get("payload", {})).lower() for e in consent_evs)
        if has_denied:
            parts.append(_finding("warn",
                "Consent Mode v2 activo con storage DENIED por defecto — "
                "GA4 corre en modo cookieless hasta aceptacion del usuario (pscdl=denied). "
                "Verificar que el CMP llame correctamente a gtag('consent','update',...)."))
        else:
            parts.append(_finding("ok", "Consent Mode v2 activo — estado granted detectado"))
    else:
        parts.append(_finding("warn",
            "Consent Mode no detectado — recomendado para cumplimiento GDPR/LPDP Peru"))

    # Cobertura GA4
    if total_urls > 0:
        ga4_pages = len(agg["all_ga4"])
        cov = ga4_pages / total_urls
        if cov >= 0.8:
            parts.append(_finding("ok",
                f"GA4 disparando en {ga4_pages}/{total_urls} URLs auditadas ({cov:.0%})"))
        else:
            parts.append(_finding("warn",
                f"GA4 solo en {ga4_pages}/{total_urls} URLs ({cov:.0%}) — "
                f"revisar paginas sin hits"))

    # Headless note
    if any("HeadlessChrome" in str(h.get("raw", {}).get("uafvl", "")) for h in agg["all_ga4"]):
        parts.append(_finding("info",
            "Auditoria en modo headless — Hotjar, Clarity y algunos chat widgets "
            "pueden no cargar. Para validarlos usar modo 'assisted' o --headless false."))

    return f"""
<div class="card">
  <div class="card-title">Hallazgos y Diagnostico</div>
  {''.join(parts)}
</div>"""


def _sec_coverage_table(data: dict) -> str:
    rows: list[str] = []
    for journey in data.get("journeys", []):
        jname = journey.get("journey_name", journey.get("journey_id", ""))
        for step in journey.get("steps", []):
            url      = step.get("url", step.get("requested_url", ""))
            path     = re.sub(r"https?://[^/]+", "", url) or "/"
            stype    = step.get("type", "")
            dl_count = len(step.get("new_datalayer_events", []))
            ga4_count= len(step.get("new_ga4_hits", []))
            status   = step.get("status", "")

            has_consent = any(
                "consent" in str(e.get("payload", {})).lower()
                for e in step.get("new_datalayer_events", [])
            )

            # Eventos custom (no GTM built-in)
            _skip_prefixes = ("gtm.", "optimize.")
            _skip_keys     = ("consent_default", "consent_update")
            custom = [
                e.get("payload", {}).get("event", "")
                for e in step.get("new_datalayer_events", [])
                if e.get("payload", {}).get("event")
                and not any(e["payload"]["event"].startswith(p) for p in _skip_prefixes)
                and e["payload"]["event"] not in _skip_keys
                and e.get("payload", {}).get("0") not in ("consent", "config", "js")
            ]

            custom_html = (
                " ".join(
                    f'<span style="background:#e9d8fd;color:#553c9a;padding:1px 6px;'
                    f'border-radius:3px;font-size:.72rem">{_esc(ev)}</span>'
                    for ev in custom[:5]
                ) or '<span style="color:var(--muted);font-size:.78rem">&mdash;</span>'
            )

            cmp_html = (
                '<span style="background:#c6f6d5;color:#22543d;padding:1px 6px;'
                'border-radius:3px;font-size:.72rem;font-weight:600">CMP</span>'
                if has_consent else "&mdash;"
            )

            status_html = (
                '<span style="color:#38a169;font-weight:600">OK</span>'
                if status == "ok"
                else f'<span style="color:#e53e3e">{_esc(status)}</span>'
            )

            rows.append(
                f"<tr>"
                f"<td style='font-size:.8rem'><strong>{_esc(path)}</strong>"
                f"<div style='color:var(--muted);font-size:.72rem'>{_esc(jname)}</div></td>"
                f"<td style='font-size:.78rem'>{_esc(stype)}</td>"
                f"<td style='text-align:center'>{dl_count}</td>"
                f"<td style='text-align:center'>{ga4_count}</td>"
                f"<td style='text-align:center'>{cmp_html}</td>"
                f"<td>{custom_html}</td>"
                f"<td>{status_html}</td>"
                f"</tr>"
            )

    return f"""
<div class="card">
  <div class="card-title">Cobertura por URL</div>
  <div class="tbl-wrap">
    <table>
      <tr>
        <th>URL / Journey</th><th>Tipo</th>
        <th style="text-align:center">dataLayer</th>
        <th style="text-align:center">GA4</th>
        <th style="text-align:center">Consent</th>
        <th>Eventos custom</th>
        <th>Estado</th>
      </tr>
      {''.join(rows)}
    </table>
  </div>
</div>"""


def _sec_journey_details(data: dict) -> str:
    parts: list[str] = []
    for journey in data.get("journeys", []):
        jname    = journey.get("journey_name", journey.get("journey_id", ""))
        steps    = journey.get("steps", [])
        dl_evs   = journey.get("datalayer_events", [])
        ga4_hits = journey.get("ga4_hits", [])

        inner = (
            f'<div class="card-body">'
            f'{_sec_datalayer(dl_evs)}'
            f'{_sec_ga4_hits(ga4_hits)}'
            f'</div>'
        )
        parts.append(f"""
<details class="card">
  <summary>
    <div class="card-title">
      {_esc(jname)}
      <span style="font-weight:400;color:var(--muted);margin-left:12px;font-size:.82rem">
        {len(steps)} URLs &middot; {len(dl_evs)} dl events &middot; {len(ga4_hits)} GA4 hits
      </span>
    </div>
  </summary>
  {inner}
</details>""")

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada público
# ──────────────────────────────────────────────────────────────────────────────

def generate_site_audit_html(data: dict[str, Any], output_dir: str = "reports") -> Path:
    """
    Genera un reporte HTML standalone desde un site_audit_results.json.
    Retorna el path al archivo HTML.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    domain   = re.sub(r"[^\w]", "_", data.get("domain", "unknown"))[:50]
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = out / f"{domain}_site_report_{ts}.html"

    agg      = _aggregate(data)
    now_fmt  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    gtm_mock = {
        "gtm_ids": agg["gtm_ids"],
        "ga4_ids": agg["ga4_ids"],
        "has_gtm_object": bool(agg["gtm_ids"]),
        "third_party": agg["third_party"],
    }

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tag Audit Site-Wide &mdash; {_esc(data.get("domain", ""))}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_sec_header(data, agg)}
{_sec_ids(gtm_mock, agg["ga4_ids"], agg["pixels"], agg["third_party"])}
{_sec_findings(data, agg)}
{_sec_coverage_table(data)}
{_sec_journey_details(data)}
<div class="footer">tag_auditor &mdash; site-wide &mdash; generado el {_esc(now_fmt)}</div>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    return html_path
