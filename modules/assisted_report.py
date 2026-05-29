"""
Generador de reportes HTML para auditorías en modo assisted (navegación manual).
Complementa report_generator.py para sesiones donde el auditor navega manualmente.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

from modules.report_generator import (
    _CSS,
    _esc,
    _ts,
    _sec_ids,
    _sec_datalayer,
    _sec_ga4_hits,
)


# ──────────────────────────────────────────────────────────────────────────────
# Secciones específicas del modo asistido
# ──────────────────────────────────────────────────────────────────────────────

def _stat_box(count: int | str, label: str) -> str:
    return (
        f'<div style="text-align:center;background:rgba(255,255,255,.12);'
        f'border-radius:8px;padding:10px 16px;min-width:72px">'
        f'<div style="font-size:1.6rem;font-weight:700;color:#e2e8f0">{count}</div>'
        f'<div style="font-size:.68rem;color:#a0aec0;text-transform:uppercase;'
        f'letter-spacing:.1em">{_esc(label)}</div></div>'
    )


def _sec_header_assisted(data: dict) -> str:
    domain = data.get("domain", "")
    captured_at = data.get("captured_at", "")[:19].replace("T", " ")
    dl_count = data.get("datalayer_count", 0)
    ga4_count = data.get("ga4_count", 0)
    px_count = data.get("pixel_count", 0)

    spa_count = sum(
        1 for e in data.get("datalayer_events", [])
        if e.get("payload", {}).get("event") == "gtm.historyChange-v2"
    )

    start_url = data.get("start_url", "")
    final_url = data.get("final_url", "")

    return f"""
<div class="hdr">
  <div class="hdr-left">
    <div class="tool-tag">Tag Audit &mdash; Modo Asistido / Navegacion Manual</div>
    <h1>{_esc(domain)}</h1>
    <div class="hdr-meta">
      <span><strong>Inicio:</strong> {_esc(start_url)}</span>
      <span><strong>Final:</strong> {_esc(final_url)}</span>
      <span><strong>Fecha:</strong> {_esc(captured_at)}</span>
    </div>
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    {_stat_box(dl_count, "dataLayer")}
    {_stat_box(ga4_count, "GA4 hits")}
    {_stat_box(px_count, "pixel hits")}
    {_stat_box(spa_count, "SPA navs")}
  </div>
</div>"""


def _sec_findings(data: dict) -> str:
    gtm_info = data.get("gtm_info", {})
    ga4_ids = data.get("measurement_ids", [])
    gtm_ids = gtm_info.get("gtm_ids", [])
    third_party = gtm_info.get("third_party", {})
    dl_events = data.get("datalayer_events", [])
    ga4_hits = data.get("ga4_hits", [])
    pixel_hits = data.get("pixel_hits", [])

    spa_navs = [
        e for e in dl_events
        if e.get("payload", {}).get("event") == "gtm.historyChange-v2"
    ]
    ga4_pageviews = [h for h in ga4_hits if h.get("event_name") == "page_view"]
    meta_pageviews = [p for p in pixel_hits if re.search(r'[?&]ev=PageView', p.get("url", ""))]

    findings: list[tuple[str, str]] = []

    for gid in gtm_ids:
        findings.append(("ok", f"GTM activo: {gid}"))
    if not gtm_ids:
        findings.append(("warn", "GTM no detectado en window.google_tag_manager"))

    for gid in ga4_ids:
        findings.append(("ok", f"GA4 configurado: {gid}"))

    if third_party.get("meta_pixel"):
        meta_id = ""
        for p in pixel_hits[:5]:
            m = re.search(r'[?&]id=(\d{10,})', p.get("url", ""))
            if m:
                meta_id = m.group(1)
                break
        findings.append(("ok", f"Meta Pixel activo{' (ID: ' + meta_id + ')' if meta_id else ''}"))

    if third_party.get("google_ads"):
        findings.append(("ok", "Google Ads detectado (network request)"))
    if third_party.get("hotjar"):
        findings.append(("info", "Hotjar detectado"))
    if third_party.get("clarity"):
        findings.append(("info", "Microsoft Clarity detectado"))
    if third_party.get("tiktok"):
        findings.append(("info", "TikTok Pixel detectado"))
    if third_party.get("linkedin"):
        findings.append(("info", "LinkedIn Insight Tag detectado"))

    if spa_navs:
        findings.append(("info",
            f"Angular / SPA detectada — {len(spa_navs)} navegaciones via "
            f"historyChange (pushState / replaceState)"))

    # Hallazgo clave: brecha GA4 en SPA
    if spa_navs:
        total_pages = len(spa_navs) + 1
        ratio = len(ga4_pageviews) / total_pages
        if ratio < 0.5:
            findings.append(("critical",
                f"GA4 NO registra page_view en navegaciones SPA — solo {len(ga4_pageviews)} hit "
                f"de {total_pages} paginas visitadas. "
                f"Solucion: crear trigger 'History Change' en GTM y vincularlo al tag "
                f"GA4 Event (event_name: page_view) o a la Configuration Tag con "
                f"'Send Page View' habilitado."))
        else:
            findings.append(("ok",
                f"GA4 registra page_view en navegaciones SPA "
                f"({len(ga4_pageviews)} hits / {total_pages} paginas)"))

    if meta_pageviews and spa_navs:
        pv_ok = len(meta_pageviews) >= len(spa_navs)
        findings.append(("ok" if pv_ok else "warn",
            f"Meta Pixel PageView en SPA: {len(meta_pageviews)} hits "
            f"(vs {len(spa_navs)} navegaciones SPA)"))

    icons = {"ok": "✅", "warn": "⚠️", "critical": "🔴", "info": "ℹ️"}
    bg_map = {"ok": "#f0fff4", "warn": "#fffff0", "critical": "#fff5f5", "info": "#ebf8ff"}
    fg_map = {"ok": "#22543d", "warn": "#744210", "critical": "#742a2a", "info": "#2a4365"}

    items = "\n".join(
        f'<div style="padding:10px 16px;border-radius:6px;margin-bottom:8px;'
        f'background:{bg_map[f]};color:{fg_map[f]};font-size:.88rem;line-height:1.6">'
        f'{icons[f]} {_esc(msg)}</div>'
        for f, msg in findings
    )

    return f"""
<div class="card">
  <div class="card-title">Hallazgos y Diagnostico</div>
  {items}
</div>"""


def _sec_spa_timeline(dl_events: list) -> str:
    spa_navs = [
        e for e in dl_events
        if e.get("payload", {}).get("event") == "gtm.historyChange-v2"
    ]
    if not spa_navs:
        return ""

    rows: list[str] = []
    for ev in spa_navs:
        p = ev.get("payload", {})
        old_url = p.get("gtm.oldUrl", "")
        new_url = p.get("gtm.newUrl", "")
        source = p.get("gtm.historyChangeSource", "")

        old_path = re.sub(r"https?://[^/]+", "", old_url) or "/"
        new_path = re.sub(r"https?://[^/]+", "", new_url) or "/"

        src_badge = (
            f'<span style="background:#ebf4ff;color:#2b6cb0;padding:1px 7px;'
            f'border-radius:4px;font-size:.72rem;font-weight:600">{_esc(source)}</span>'
        )
        rows.append(
            f"<tr>"
            f"<td style='white-space:nowrap'>{_ts(ev.get('ts'))}</td>"
            f"<td style='color:var(--muted);font-size:.8rem'>{_esc(old_path)}</td>"
            f"<td style='text-align:center;color:var(--muted);padding:7px 6px'>&rarr;</td>"
            f"<td><strong style='font-size:.82rem'>{_esc(new_path)}</strong></td>"
            f"<td>{src_badge}</td>"
            f"</tr>"
        )

    return f"""
<details class="card" open>
  <summary><div class="card-title">Navegacion SPA &mdash; {len(spa_navs)} historyChange detectados</div></summary>
  <div class="card-body">
    <div class="tbl-wrap">
      <table>
        <tr><th>Hora</th><th>Desde</th><th></th><th>Hacia</th><th>Metodo</th></tr>
        {''.join(rows)}
      </table>
    </div>
  </div>
</details>"""


def _sec_pixel_events(pixel_hits: list) -> str:
    if not pixel_hits:
        return ""

    rows: list[str] = []
    for p in pixel_hits:
        url = p.get("url", "")

        ev_m = re.search(r'[?&]ev=([^&]+)', url)
        ev_name = unquote_plus(ev_m.group(1)) if ev_m else "?"

        dl_m = re.search(r'[?&]dl=([^&]+)', url)
        page = unquote_plus(dl_m.group(1)) if dl_m else ""
        page_path = re.sub(r"https?://[^/]+", "", page) or "/"

        btn_m = re.search(r'buttonText=([^&]+?)(?:&|$)', url)
        btn = unquote_plus(btn_m.group(1)).replace("\n", " ")[:60] if btn_m else ""

        detail_html = f'<span style="color:var(--muted)">{_esc(page_path)}</span>'
        if btn:
            detail_html += (
                f' <span style="font-size:.76rem;color:#805ad5;margin-left:6px">'
                f'&#9658; {_esc(btn)}</span>'
            )

        rows.append(
            f"<tr>"
            f"<td style='white-space:nowrap'>{_ts(p.get('timestamp'))}</td>"
            f"<td><strong>{_esc(ev_name)}</strong></td>"
            f"<td style='font-size:.8rem'>{detail_html}</td>"
            f"</tr>"
        )

    pageview_count = sum(
        1 for p in pixel_hits if re.search(r'[?&]ev=PageView', p.get("url", ""))
    )

    return f"""
<details class="card">
  <summary><div class="card-title">Meta Pixel &mdash; {len(pixel_hits)} hits ({pageview_count} PageViews)</div></summary>
  <div class="card-body">
    <div class="tbl-wrap">
      <table>
        <tr><th>Hora</th><th>Evento</th><th>Pagina / Detalle</th></tr>
        {''.join(rows)}
      </table>
    </div>
  </div>
</details>"""


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada público
# ──────────────────────────────────────────────────────────────────────────────

def generate_assisted_html(data: dict[str, Any], output_dir: str = "reports") -> Path:
    """
    Genera un reporte HTML standalone desde un JSON de auditoría asistida.
    Retorna el path al archivo HTML generado.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    domain = re.sub(r"[^\w]", "_", data.get("domain", "unknown"))[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = out / f"{domain}_assisted_report_{ts}.html"

    gtm_info = data.get("gtm_info", {})
    ga4_ids = data.get("measurement_ids", [])
    pixels = data.get("detected_pixels", [])
    now_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tag Audit Asistido &mdash; {_esc(data.get("domain", ""))}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_sec_header_assisted(data)}
{_sec_ids(gtm_info, ga4_ids, pixels, gtm_info.get("third_party", {}))}
{_sec_findings(data)}
{_sec_spa_timeline(data.get("datalayer_events", []))}
{_sec_pixel_events(data.get("pixel_hits", []))}
{_sec_datalayer(data.get("datalayer_events", []))}
{_sec_ga4_hits(data.get("ga4_hits", []))}
<div class="footer">tag_auditor &mdash; modo asistido &mdash; generado el {_esc(now_fmt)}</div>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    return html_path
