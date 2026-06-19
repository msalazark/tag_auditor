"""
crawl.py — Descubre y agrupa URLs de un sitio por patrón de ruta.

Paso 1 del flujo de auditoría: identifica qué tipos de páginas existen
antes de seleccionar manualmente cuáles auditar.

Uso:
    python crawl.py --url https://www.sitio.com
    python crawl.py --url https://www.sitio.com --out reports/urls.json
    python crawl.py --url https://www.sitio.com --headless false
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click

from site_crawler import SiteCrawler


def _is_content_slug(segment: str) -> bool:
    """True si el segmento parece un slug de contenido (artículo, noticia),
    no una sección navegable del sitio."""
    return segment.count("-") >= 4 or len(segment) > 35


def _get_pattern(url: str) -> str:
    """Reduce una URL a su patrón de ruta agrupable.

    Lógica:
    - 0 segmentos             → /
    - 1 segmento              → /{seg1}/
    - 2+ segmentos, seg2 es slug de contenido → /{seg1}/*/   (ej. /noticias/titulo-largo)
    - 2+ segmentos, seg2 es sección          → /{seg1}/{seg2}/
    """
    path = urlparse(url).path.rstrip("/") or "/"
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "/"
    if len(segments) == 1:
        return f"/{segments[0]}/"
    if _is_content_slug(segments[1]):
        return f"/{segments[0]}/*/"
    return "/" + "/".join(segments[:2]) + "/"


def _group_urls(url_records: list[dict]) -> list[dict]:
    """Agrupa URLs por patrón de ruta y detecta si hay niveles más profundos."""
    groups: dict[str, list[str]] = defaultdict(list)

    for item in url_records:
        key = _get_pattern(item["url"])
        groups[key].append(item["url"])

    result = []
    for pattern, urls in sorted(groups.items()):
        has_deeper = any(
            len([s for s in urlparse(u).path.strip("/").split("/") if s]) > 2
            for u in urls
        )
        display = pattern.rstrip("/") + "/*/" if (has_deeper and len(urls) > 1) else pattern
        result.append({
            "pattern": display,
            "count": len(urls),
            "example": urls[0],
            "urls": urls,
        })

    return result


def _print_table(domain: str, source: str, groups: list[dict], out_path: Path) -> None:
    total = sum(g["count"] for g in groups)
    col_w = max((len(g["pattern"]) for g in groups), default=20) + 2

    click.echo(f"\n  Dominio   : {domain}")
    click.echo(f"  URLs      : {total}  (fuente: {source})")
    click.echo(f"\n  {'Patron':<{col_w}}  {'URLs':>5}   Ejemplo")
    click.echo("  " + "-" * (col_w + 50))

    for g in groups:
        example = g["example"]
        if len(example) > 55:
            example = example[:52] + "..."
        click.echo(f"  {g['pattern']:<{col_w}}  {g['count']:>5}   {example}")

    click.echo(f"\n  JSON guardado en : {out_path}")
    click.echo(
        "\n  Siguiente paso   : selecciona una URL por tipo de pagina y audita con\n"
        "    python main.py --url <URL> --spec specs/<spec>.json\n"
    )


@click.command()
@click.option("--url",      required=True, help="URL raiz del sitio a crawlear")
@click.option("--out",      default=None,  help="Archivo JSON de salida (default: reports/{domain}_urls.json)")
@click.option("--headless", default="true", show_default=True, help="Modo headless: true/false")
@click.option("--timeout",  default=3, show_default=True, type=int, help="Segundos de espera por pagina (crawl superficial)")
@click.option("--session",  default=None, help="Sesion guardada para sitios con login (login_helper.py)")
def main(url: str, out: str | None, headless: str, timeout: int, session: str | None) -> None:
    """Descubre URLs del sitio y las muestra agrupadas por patron de ruta."""
    headless_bool = headless.lower() not in ("false", "0", "no")

    crawler = SiteCrawler(
        root_url=url,
        output_dir="reports",
        timeout=timeout,
        headless=headless_bool,
        session_file=session,
    )

    click.echo(f"\n  Crawleando : {url}")
    if session:
        click.echo(f"  Sesion     : {session}")
    click.echo("  Buscando sitemap / robots.txt / crawl superficial...\n")

    result = asyncio.run(crawler.discover())

    groups = _group_urls(result.get("urls", []))

    # Enriquecer el JSON con los grupos
    result["patterns"] = groups

    # Determinar path de salida
    domain = result.get("domain", "sitio").replace(".", "_")
    out_path = Path(out) if out else Path("reports") / f"{domain}_urls.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_table(result.get("domain", url), result.get("source", "?"), groups, out_path)


if __name__ == "__main__":
    main()
