"""
CLI entry point del Tag Audit Tool.
Uso: python main.py --url https://example.com [--headless false] [--timeout 5]
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from auditor import TagAuditor


@click.command()
@click.option("--url", required=True, help="URL a auditar")
@click.option(
    "--spec",
    default="specs/default_spec.json",
    show_default=True,
    help="Path al JSON de spec de eventos",
)
@click.option(
    "--headless",
    default="true",
    show_default=True,
    help="Modo headless del browser: true/false",
)
@click.option(
    "--timeout",
    default=3,
    show_default=True,
    type=int,
    help="Segundos de espera adicional tras networkidle",
)
@click.option(
    "--output",
    default="reports",
    show_default=True,
    help="Carpeta de output para reportes",
)
def main(url: str, spec: str, headless: str, timeout: int, output: str) -> None:
    """Tag Audit Tool -- audita el etiquetado GTM/GA4/dataLayer de una URL."""
    headless_bool = headless.lower() not in ("false", "0", "no")

    if not Path(spec).exists():
        click.echo(f"[error] No se encontro el archivo de spec: {spec}", err=True)
        sys.exit(1)

    click.echo(f"\n  Auditando: {url}")
    click.echo(f"  Spec:      {spec}")
    click.echo(f"  Headless:  {headless_bool}")
    click.echo(f"  Timeout:   {timeout}s extra\n")

    auditor = TagAuditor(
        spec_path=spec,
        headless=headless_bool,
        timeout=timeout,
        output_dir=output,
    )

    results = asyncio.run(auditor.run(url))

    # Resumen en consola
    gtm = results["gtm_info"]
    val = results["validation"]

    gtm_ids = ", ".join(gtm.get("gtm_ids", [])) or "No detectado"
    ga4_ids = ", ".join(
        sorted({
            *gtm.get("ga4_ids", []),
            *[h["measurement_id"] for h in results["ga4_hits"] if h.get("measurement_id")],
        })
    ) or "No detectado"
    pixels = ", ".join(results["pixel_types"]) or "Ninguno"

    sep = "-" * 60
    click.echo(sep)
    click.echo(f"  GTM ID detectado:      {gtm_ids}")
    click.echo(f"  GA4 ID detectado:      {ga4_ids}")
    click.echo(f"  Otros pixels:          {pixels}")
    click.echo(f"  dataLayer events:      {len(results['datalayer_events'])}")
    click.echo(f"  GA4 hits:              {len(results['ga4_hits'])}")
    click.echo(f"  Score de cobertura:    {val['coverage_score']}%  ({val['ok_count']}/{val['total_count']} OK)")

    if val["gaps"]:
        click.echo(f"\n  Brechas ({len(val['gaps'])}):")
        for gap in val["gaps"]:
            miss = ", ".join(gap["missing_params"]) or "evento no disparado"
            click.echo(f"    [{gap['priority']}] {gap['event_name']} -- {gap['status']} -- faltan: {miss}")

    click.echo("\n  Reportes generados:")
    click.echo(f"    HTML: {results['html_report']}")
    click.echo(f"    JSON: {results['json_report']}")
    click.echo(sep + "\n")


if __name__ == "__main__":
    main()
