"""
assisted_urls.py — Extrae URLs navegadas durante una sesión asistida.

Lee el JSON generado por `site_main.py assisted` y extrae todas las URLs
únicas capturadas via gtm.historyChange-v2, page_location y GA4 hits.
Produce el mismo formato JSON que crawl.py para ser procesado por crawl_report.py.

Uso:
    python assisted_urls.py reports/construyexperto_pe_assisted_*.json
    python assisted_urls.py reports/assisted.json --out reports/mis_urls.json
    python assisted_urls.py reports/assisted.json --report   # genera HTML directo
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, urldefrag

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click


# ─────────────────────────────────────────────────────────────────────────────
# Extracción de URLs
# ─────────────────────────────────────────────────────────────────────────────

def _clean(url: str) -> str:
    url, _ = urldefrag(url.strip())
    return url.rstrip("/") or url


def _same_domain(url: str, domain: str) -> bool:
    return urlparse(url).netloc == domain


def extract_urls(data: dict) -> list[str]:
    """Extrae todas las URLs únicas navegadas durante la sesión asistida."""
    domain = data.get("domain", "")
    seen: dict[str, float] = {}  # url → timestamp para ordenar

    def _add(url: str, ts: float = 0.0) -> None:
        if not url or not url.startswith("http"):
            return
        cleaned = _clean(url)
        if not _same_domain(cleaned, domain):
            return
        if cleaned not in seen:
            seen[cleaned] = ts

    # 1. visited_urls registradas por el instrumentador
    for item in data.get("visited_urls", []):
        _add(item.get("url", ""), item.get("ts", 0))

    # 2. final_url (última página al presionar Enter)
    _add(data.get("final_url", ""), float("inf"))

    # 3. gtm.historyChange-v2 → gtm.newUrl (navegación SPA)
    for ev in data.get("datalayer_events", []):
        payload = ev.get("payload", {})
        ts = ev.get("ts", 0)
        if payload.get("event") == "gtm.historyChange-v2":
            _add(payload.get("gtm.newUrl", ""), ts)
            _add(payload.get("gtm.oldUrl", ""), ts)

    # 4. page_location en pushes de config GA4
    for ev in data.get("datalayer_events", []):
        payload = ev.get("payload", {})
        ts = ev.get("ts", 0)
        for val in payload.values():
            if isinstance(val, dict):
                loc = val.get("page_location", "")
                if loc:
                    _add(loc, ts)

    # 5. GA4 hits interceptados
    for hit in data.get("ga4_hits", []):
        _add(hit.get("page_location", ""), hit.get("timestamp", 0))

    # Ordenar por timestamp de primera aparición
    return [url for url, _ in sorted(seen.items(), key=lambda x: x[1])]


# ─────────────────────────────────────────────────────────────────────────────
# Agrupamiento por patrón (mismo algoritmo que crawl.py)
# ─────────────────────────────────────────────────────────────────────────────

def _is_content_slug(segment: str) -> bool:
    return segment.count("-") >= 4 or len(segment) > 35


def _get_pattern(url: str) -> str:
    path = urlparse(url).path.rstrip("/") or "/"
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "/"
    if len(segments) == 1:
        return f"/{segments[0]}/"
    if _is_content_slug(segments[1]):
        return f"/{segments[0]}/*/"
    return "/" + "/".join(segments[:2]) + "/"


def group_urls(urls: list[str], domain: str) -> list[dict]:
    groups: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        groups[_get_pattern(url)].append(url)

    result = []
    for pattern, group_urls in sorted(groups.items()):
        has_deeper = any(
            len([s for s in urlparse(u).path.strip("/").split("/") if s]) > 2
            for u in group_urls
        )
        display = pattern.rstrip("/") + "/*/" if (has_deeper and len(group_urls) > 1) else pattern
        result.append({
            "pattern": display,
            "count": len(group_urls),
            "example": group_urls[0],
            "urls": group_urls,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("assisted_json", metavar="ASSISTED_JSON")
@click.option("--out",    default=None, help="Path del JSON de salida (default: junto al JSON de entrada)")
@click.option("--report", is_flag=True, default=False, help="Generar también el reporte HTML con crawl_report.py")
@click.option("--spec",   default="specs/example_corporate.json", show_default=True,
              help="Spec para los comandos sugeridos en el reporte HTML")
def main(assisted_json: str, out: str | None, report: bool, spec: str) -> None:
    """Extrae URLs navegadas del JSON asistido y produce un JSON compatible con crawl_report.py."""
    src = Path(assisted_json)
    if not src.exists():
        click.echo(f"\n  [ERROR] Archivo no encontrado: {src}", err=True)
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))

    if data.get("mode") != "assisted":
        click.echo("\n  [WARN] El JSON no parece ser de modo asistido (mode != 'assisted').")

    urls = extract_urls(data)
    domain = data.get("domain", urlparse(data.get("start_url", "")).netloc)
    patterns = group_urls(urls, domain)

    url_records = [
        {
            "url": u,
            "path": urlparse(u).path or "/",
            "depth": 0,
            "discovered_from": "assisted",
            "allowed": True,
        }
        for u in urls
    ]

    result = {
        "domain": domain,
        "discovered_at": data.get("captured_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "source": "assisted",
        "total_urls": len(urls),
        "disallowed_paths": [],
        "urls": url_records,
        "patterns": patterns,
    }

    out_path = Path(out) if out else src.with_name(src.stem + "_urls.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Consola
    col_w = max((len(p["pattern"]) for p in patterns), default=20) + 2
    click.echo(f"\n  Dominio    : {domain}")
    click.echo(f"  Sesion     : {src.name}")
    click.echo(f"  URLs únicas: {len(urls)}  |  Patrones: {len(patterns)}")
    click.echo(f"\n  {'Patron':<{col_w}}  {'URLs':>5}   Ejemplo")
    click.echo("  " + "-" * (col_w + 50))
    for p in patterns:
        ex = p["example"][:55] + "..." if len(p["example"]) > 55 else p["example"]
        click.echo(f"  {p['pattern']:<{col_w}}  {p['count']:>5}   {ex}")

    click.echo(f"\n  JSON guardado en : {out_path}")

    if report:
        click.echo("")
        subprocess.run(
            [sys.executable, "crawl_report.py", str(out_path), "--spec", spec],
            check=False,
        )
    else:
        click.echo(
            f"\n  Para generar el reporte HTML:\n"
            f"    python crawl_report.py {out_path} --spec {spec}\n"
        )


if __name__ == "__main__":
    main()
