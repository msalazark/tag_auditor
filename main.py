"""
CLI entry point v2 del Tag Audit Tool.
Uso: python main.py --url URL --spec specs/example_corporate.json
"""
from __future__ import annotations

import asyncio
import sys

# Forzar UTF-8 en consola Windows para los simbolos unicode
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click

from auditor import SpecError, TagAuditor


@click.command()
@click.option("--url",  required=True, help="URL a auditar")
@click.option("--spec", required=True, help="Path al JSON de spec del usuario")
@click.option("--headless", default="true", show_default=True,
              help="Modo headless del browser: true/false")
@click.option("--timeout", default=3, show_default=True, type=int,
              help="Segundos de espera adicional tras networkidle")
@click.option("--output", default="reports", show_default=True,
              help="Carpeta de output para reportes")
@click.option("--session", default=None, show_default=True,
              help="Path al JSON de sesion generado por login_helper.py (para sitios con login)")
def main(url: str, spec: str, headless: str, timeout: int, output: str, session: str | None) -> None:
    """Tag Audit Tool v2 -- audita GTM/GA4/dataLayer contra una spec personalizada."""
    headless_bool = headless.lower() not in ("false", "0", "no")

    click.echo(f"\n  Auditando : {url}")
    click.echo(f"  Spec      : {spec}")
    click.echo(f"  Headless  : {headless_bool}")
    click.echo(f"  Timeout   : {timeout}s extra")
    if session:
        click.echo(f"  Sesion    : {session}")
    click.echo("")

    auditor = TagAuditor(
        spec_path=spec,
        headless=headless_bool,
        timeout=timeout,
        output_dir=output,
        session_path=session,
    )

    try:
        results = asyncio.run(auditor.run(url))
    except SpecError as exc:
        click.echo(f"\n  [ERROR] {exc}", err=True)
        sys.exit(1)

    # ── Resumen en consola ────────────────────────────────────────────────────
    gtm    = results["gtm_info"]
    val    = results["validation"]
    scores = val.get("scores", {})
    gaps   = val.get("gaps", [])

    gtm_ids = ", ".join(gtm.get("gtm_ids", [])) or "No detectado"
    ga4_ids = ", ".join(sorted({
        *gtm.get("ga4_ids", []),
        *[h["measurement_id"] for h in results["ga4_hits"] if h.get("measurement_id")],
    })) or "No detectado"
    pixels = ", ".join(results["pixel_types"]) or "Ninguno"

    tp = gtm.get("third_party", {})

    click.echo("  " + "-" * 56)
    click.echo(f"  [GTM]  {gtm_ids}")
    click.echo(f"  [GA4]  {ga4_ids}")

    # Pixels y terceros
    pixel_map = {
        "meta":       "Meta Pixel",
        "hotjar":     "Hotjar",
        "clarity":    "Microsoft Clarity",
        "linkedin":   "LinkedIn Insight",
        "tiktok":     "TikTok Pixel",
        "google_ads": "Google Ads",
        "twitter":    "Twitter/X",
    }
    detected_px  = set(results["pixel_types"])
    all_tp_keys  = set(pixel_map.keys())
    for key, label in pixel_map.items():
        sym = "[OK]" if (key in detected_px or tp.get(key)) else "[--]"
        click.echo(f"  {sym}  {label}")

    # Scores
    def _s(key: str) -> str:
        s = scores.get(key, {})
        return f"{s.get('ok',0)}/{s.get('total',0)} ({s.get('pct',0):.0f}%)"

    click.echo("")
    click.echo(f"  Score P1 (criticos)  : {_s('p1')}")
    click.echo(f"  Score ecommerce      : {_s('ecommerce')}")
    click.echo(f"  Score leads          : {_s('leads')}")
    click.echo(f"  Score custom         : {_s('custom')}")
    click.echo(f"  Score global         : {_s('global')}")

    if gaps:
        click.echo(f"\n  Brechas ({len(gaps)}):")
        for g in gaps[:10]:  # maximo 10 en consola
            miss = ", ".join(g["missing_params"]) or "evento no disparado"
            click.echo(f"    [{g['priority']}] {g['event_name']} [{g['status']}] -- {miss}")
        if len(gaps) > 10:
            click.echo(f"    ... y {len(gaps)-10} mas (ver reporte HTML)")

    click.echo(f"\n  Reporte : {results['html_report']}")
    click.echo("  " + "-" * 56 + "\n")


if __name__ == "__main__":
    main()
