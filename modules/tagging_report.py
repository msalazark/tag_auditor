"""
Generador de reportes HTML para el Tag Opportunity Planner.
Produce un reporte con matriz esfuerzo/valor, backlog priorizado y guía GTM.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.report_generator import _CSS, _esc


# ── Helpers de render ─────────────────────────────────────────────────────────

def _badge(text: str, color: str = "#718096", bg: str = "#f7fafc") -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'font-size:.72rem;font-weight:700;text-transform:uppercase;'
        f'background:{bg};color:{color}">{_esc(text)}</span>'
    )


_PRIORITY_STYLE = {
    "P1": ("#742a2a", "#fed7d7"),
    "P2": ("#744210", "#fefcbf"),
    "P3": ("#4a5568", "#e2e8f0"),
}
_VALUE_STYLE = {
    "high":   ("#22543d", "#c6f6d5"),
    "medium": ("#744210", "#fefcbf"),
    "low":    ("#4a5568", "#e2e8f0"),
}

_VALUE_ES = {"high": "Alto", "medium": "Medio", "low": "Bajo"}


def _priority_badge(p: str) -> str:
    c, bg = _PRIORITY_STYLE.get(p, ("#4a5568", "#e2e8f0"))
    return _badge(p, c, bg)


def _value_badge(v: str) -> str:
    c, bg = _VALUE_STYLE.get(v, ("#4a5568", "#e2e8f0"))
    return _badge(_VALUE_ES.get(v, v), c, bg)


def _effort_bar(hours: float) -> str:
    max_h = 4.0
    pct = min(100, int(hours / max_h * 100))
    color = "#38a169" if hours <= 1 else ("#d69e2e" if hours <= 2 else "#e53e3e")
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<div style="flex:1;background:#edf2f7;border-radius:999px;height:6px">'
        f'<div style="width:{pct}%;background:{color};height:100%;border-radius:999px"></div>'
        f'</div>'
        f'<span style="font-size:.75rem;color:#4a5568;white-space:nowrap">{hours}h</span>'
        f'</div>'
    )


# ── Secciones del reporte ─────────────────────────────────────────────────────

def _sec_header(domain: str, pages: int, total_opps: int, total_hours: float,
                model: str, cost_usd: float, now_fmt: str) -> str:
    def stat(n: Any, label: str) -> str:
        return (
            f'<div style="text-align:center;background:rgba(255,255,255,.12);'
            f'border-radius:8px;padding:10px 16px;min-width:80px">'
            f'<div style="font-size:1.6rem;font-weight:700;color:#e2e8f0">{n}</div>'
            f'<div style="font-size:.68rem;color:#a0aec0;text-transform:uppercase;'
            f'letter-spacing:.1em">{_esc(label)}</div></div>'
        )

    return f"""
<div class="hdr">
  <div class="hdr-left">
    <div class="tool-tag">Tag Opportunity Planner &mdash; Analisis con IA</div>
    <h1>{_esc(domain)}</h1>
    <div class="hdr-meta">
      <span><strong>Paginas analizadas:</strong> {pages}</span>
      <span><strong>Modelo:</strong> {_esc(model)}</span>
      <span><strong>Costo analisis:</strong> ${cost_usd:.3f} USD</span>
      <span><strong>Fecha:</strong> {_esc(now_fmt)}</span>
    </div>
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    {stat(total_opps, "oportunidades")}
    {stat(f"{total_hours:.1f}h", "esfuerzo total")}
  </div>
</div>"""


def _sec_summary(all_opps: list[dict]) -> str:
    p1 = [o for o in all_opps if o["priority"] == "P1"]
    p2 = [o for o in all_opps if o["priority"] == "P2"]
    p3 = [o for o in all_opps if o["priority"] == "P3"]
    high = [o for o in all_opps if o["value"] == "high"]
    quick_wins = [o for o in all_opps if o["value"] == "high" and o["effort_hours"] <= 1]

    p1_h = sum(o["effort_hours"] for o in p1)
    all_h = sum(o["effort_hours"] for o in all_opps)

    def kpi(val: Any, label: str, sub: str = "", color: str = "#2d3748") -> str:
        return f"""
<div style="background:#fff;border-radius:10px;padding:20px 24px;
            box-shadow:0 1px 3px rgba(0,0,0,.08);flex:1;min-width:140px">
  <div style="font-size:2rem;font-weight:700;color:{color}">{val}</div>
  <div style="font-size:.85rem;font-weight:600;color:#2d3748;margin-top:2px">{_esc(label)}</div>
  <div style="font-size:.75rem;color:#718096">{_esc(sub)}</div>
</div>"""

    return f"""
<div class="card">
  <div class="card-title">Resumen Ejecutivo</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">
    {kpi(len(p1), "Eventos P1 — Criticos", f"{p1_h:.1f}h estimadas", "#742a2a")}
    {kpi(len(p2), "Eventos P2 — Importantes", f"{sum(o['effort_hours'] for o in p2):.1f}h estimadas", "#744210")}
    {kpi(len(p3), "Eventos P3 — Nice-to-have", f"{sum(o['effort_hours'] for o in p3):.1f}h estimadas", "#4a5568")}
    {kpi(f"{all_h:.1f}h", "Esfuerzo total", f"({all_h/8:.1f} días/persona)", "#2c5282")}
    {kpi(len(quick_wins), "Quick Wins", "alto valor, ≤1h c/u", "#22543d")}
  </div>
  <div style="background:#f0fff4;border-radius:8px;padding:14px 18px;font-size:.88rem;color:#22543d;border-left:4px solid #38a169">
    <strong>Recomendación de implementación:</strong> Comenzar con los {len(p1)} eventos P1
    ({p1_h:.1f}h) para cobertura básica, luego los {len(quick_wins)} quick wins de alto valor (≤1h c/u).
    Total para Sprint 1: {p1_h + sum(o['effort_hours'] for o in quick_wins if o['priority'] != 'P1'):.1f}h.
  </div>
</div>"""


def _sec_matrix(all_opps: list[dict]) -> str:
    """Matriz 2x2 Esfuerzo vs Valor con oportunidades ploteadas."""

    def quadrant(label: str, sub: str, opps: list[dict], bg: str, border: str, header_color: str) -> str:
        items = "".join(
            f'<div style="font-size:.75rem;padding:3px 6px;margin:3px 0;'
            f'background:rgba(255,255,255,.6);border-radius:4px;'
            f'border-left:3px solid {border}">'
            f'<code style="font-size:.72rem;color:#1a202c">{_esc(o["event_name"])}</code> '
            f'<span style="color:#718096">{_esc(o.get("element","")[:30])}</span>'
            f'</div>'
            for o in opps[:8]
        )
        more = f'<div style="font-size:.72rem;color:#718096;margin-top:4px">+{len(opps)-8} más</div>' if len(opps) > 8 else ""
        return f"""
<div style="background:{bg};border:2px solid {border};border-radius:10px;padding:16px;overflow:hidden">
  <div style="font-weight:700;font-size:.88rem;color:{header_color};margin-bottom:2px">{_esc(label)}</div>
  <div style="font-size:.75rem;color:#718096;margin-bottom:10px">{_esc(sub)} &mdash; <strong>{len(opps)} eventos</strong></div>
  <div style="max-height:200px;overflow-y:auto">{items}{more}</div>
</div>"""

    quick   = [o for o in all_opps if o["value"] == "high"   and o["effort_hours"] <= 1]
    major   = [o for o in all_opps if o["value"] == "high"   and o["effort_hours"] > 1]
    fillin  = [o for o in all_opps if o["value"] != "high"   and o["effort_hours"] <= 1]
    reconsider = [o for o in all_opps if o["value"] == "low" and o["effort_hours"] > 1]

    return f"""
<div class="card">
  <div class="card-title">Matriz Esfuerzo / Valor</div>
  <div style="display:grid;grid-template-columns:30px 1fr 1fr;grid-template-rows:1fr 1fr 30px;gap:8px;height:500px">
    <!-- eje Y label top -->
    <div style="grid-column:1;grid-row:1;display:flex;align-items:center;justify-content:center">
      <span style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:.72rem;font-weight:600;color:#718096">VALOR ALTO</span>
    </div>
    <!-- quick wins -->
    <div style="grid-column:2;grid-row:1">
      {quadrant("Quick Wins", "bajo esfuerzo, alto valor", quick, "#f0fff4", "#38a169", "#22543d")}
    </div>
    <!-- major projects -->
    <div style="grid-column:3;grid-row:1">
      {quadrant("Proyectos Estrategicos", "alto esfuerzo, alto valor", major, "#ebf8ff", "#3182ce", "#2c5282")}
    </div>
    <!-- eje Y label bottom -->
    <div style="grid-column:1;grid-row:2;display:flex;align-items:center;justify-content:center">
      <span style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:.72rem;font-weight:600;color:#718096">VALOR BAJO</span>
    </div>
    <!-- fill-ins -->
    <div style="grid-column:2;grid-row:2">
      {quadrant("Fill-ins", "bajo esfuerzo, valor medio/bajo", fillin, "#fffaf0", "#dd6b20", "#744210")}
    </div>
    <!-- reconsider -->
    <div style="grid-column:3;grid-row:2">
      {quadrant("Reconsiderar", "alto esfuerzo, bajo valor", reconsider, "#fff5f5", "#e53e3e", "#742a2a")}
    </div>
    <!-- eje X labels -->
    <div style="grid-column:2;grid-row:3;display:flex;align-items:center;justify-content:center">
      <span style="font-size:.72rem;font-weight:600;color:#718096">BAJO ESFUERZO (&le;1h)</span>
    </div>
    <div style="grid-column:3;grid-row:3;display:flex;align-items:center;justify-content:center">
      <span style="font-size:.72rem;font-weight:600;color:#718096">ALTO ESFUERZO (&gt;1h)</span>
    </div>
  </div>
</div>"""


def _sec_backlog(all_opps: list[dict]) -> str:
    """Tabla completa de oportunidades ordenada por prioridad y valor."""
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    value_order = {"high": 0, "medium": 1, "low": 2}
    sorted_opps = sorted(
        all_opps,
        key=lambda o: (priority_order.get(o["priority"], 9), value_order.get(o["value"], 9), o["effort_hours"])
    )

    rows = []
    current_priority = None
    for o in sorted_opps:
        if o["priority"] != current_priority:
            current_priority = o["priority"]
            c, bg = _PRIORITY_STYLE.get(current_priority, ("#4a5568", "#e2e8f0"))
            label = {"P1": "Criticos", "P2": "Importantes", "P3": "Nice-to-have"}.get(current_priority, current_priority)
            rows.append(
                f'<tr><td colspan="7" style="background:{bg};color:{c};'
                f'font-weight:700;font-size:.78rem;text-transform:uppercase;'
                f'letter-spacing:.05em;padding:7px 12px">'
                f'{current_priority} — {label}</td></tr>'
            )

        params_html = " ".join(
            f'<code style="background:#f7fafc;padding:1px 5px;border-radius:3px;font-size:.72rem">{_esc(k)}</code>'
            for k in list(o.get("parameters", {}).keys())[:4]
        ) or "—"

        rows.append(f"""<tr>
<td><strong style="font-size:.82rem">{_esc(o["event_name"])}</strong>
    <div style="color:#718096;font-size:.75rem">{_esc(o.get("element","")[:50])}</div></td>
<td style="font-size:.78rem">{_esc(o.get("element_type",""))}</td>
<td>{params_html}</td>
<td style="font-size:.78rem;color:#4a5568">{_esc(o.get("trigger","")[:60])}</td>
<td>{_effort_bar(o["effort_hours"])}</td>
<td>{_value_badge(o["value"])}</td>
<td style="font-size:.75rem;color:#718096">{_esc(o.get("gtm_tag_type","GA4 Event"))}</td>
</tr>""")

    return f"""
<details class="card" open>
  <summary><div class="card-title">Backlog de Implementacion &mdash; {len(all_opps)} oportunidades</div></summary>
  <div class="card-body">
    <div class="tbl-wrap">
      <table>
        <tr>
          <th>Evento GA4</th>
          <th>Tipo</th>
          <th>Parametros</th>
          <th>Trigger GTM</th>
          <th style="min-width:120px">Esfuerzo</th>
          <th>Valor</th>
          <th>Tag GTM</th>
        </tr>
        {''.join(rows)}
      </table>
    </div>
  </div>
</details>"""


def _sec_page_breakdown(page_results: list[dict]) -> str:
    parts = []
    for r in page_results:
        url = r["url"]
        path = re.sub(r"https?://[^/]+", "", url) or "/"
        opps = r.get("opportunities", [])
        context = r.get("business_context", "")
        page_type = r.get("page_type", "")
        total_h = sum(o["effort_hours"] for o in opps)

        rows = "".join(
            f"<tr>"
            f"<td><code style='font-size:.78rem'>{_esc(o['event_name'])}</code></td>"
            f"<td style='font-size:.78rem'>{_esc(o.get('element','')[:45])}</td>"
            f"<td>{_effort_bar(o['effort_hours'])}</td>"
            f"<td>{_value_badge(o['value'])}</td>"
            f"<td>{_priority_badge(o['priority'])}</td>"
            f"</tr>"
            for o in sorted(opps, key=lambda x: ({"P1":0,"P2":1,"P3":2}.get(x["priority"],9)))
        )

        parts.append(f"""
<details class="card">
  <summary>
    <div class="card-title">
      {_esc(path)}
      <span style="font-weight:400;color:#718096;margin-left:12px;font-size:.8rem">
        {_esc(page_type)} &middot; {len(opps)} oportunidades &middot; {total_h:.1f}h
      </span>
    </div>
  </summary>
  <div class="card-body">
    <p style="font-size:.85rem;color:#4a5568;margin-bottom:12px">{_esc(context)}</p>
    <div class="tbl-wrap">
      <table>
        <tr><th>Evento</th><th>Elemento</th><th style="min-width:100px">Esfuerzo</th><th>Valor</th><th>Prio.</th></tr>
        {rows}
      </table>
    </div>
  </div>
</details>""")

    return "\n".join(parts)


# ── Punto de entrada público ──────────────────────────────────────────────────

def generate_tagging_report(
    page_results: list[dict],
    domain: str,
    model: str,
    cost_usd: float,
    output_dir: str = "reports",
) -> Path:
    """
    Genera el reporte HTML completo del Tag Opportunity Planner.
    `page_results` es lista de dicts con url, page_type, business_context, opportunities.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w]", "_", domain)[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = out / f"{slug}_tag_plan_{ts}.html"

    all_opps = [
        {**(o.model_dump() if hasattr(o, "model_dump") else o), "_url": r["url"]}
        for r in page_results
        for o in r.get("opportunities", [])
    ]

    total_hours = sum(o["effort_hours"] for o in all_opps)
    now_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tag Plan &mdash; {_esc(domain)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_sec_header(domain, len(page_results), len(all_opps), total_hours, model, cost_usd, now_fmt)}
{_sec_summary(all_opps)}
{_sec_matrix(all_opps)}
{_sec_backlog(all_opps)}
{_sec_page_breakdown(page_results)}
<div class="footer">tag_auditor &mdash; tag opportunity planner &mdash; {_esc(now_fmt)}</div>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    return html_path
