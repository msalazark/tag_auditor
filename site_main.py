"""
CLI para auditoría site-wide con descubrimiento de URLs, clasificación y ejecución de journeys.

Comandos disponibles:
  python site_main.py audit --url example.com --output reports
  python site_main.py auth-only --auth auth/configs/lapositiva_auth.json
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Forzar UTF-8 en consola Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click

from multi_page_auditor import MultiPageAuditor


@click.group()
def cli() -> None:
    """Herramienta de auditoría de tags GA4/GTM — site-wide y autenticada."""


# ─── Comando: audit ───────────────────────────────────────────────────────────

@cli.command("audit")
@click.option("--url", required=True, help="Dominio raíz o URL de inicio para auditoría site-wide")
@click.option("--spec", default=None, help="Path opcional al JSON de spec para filtrar eventos")
@click.option("--headless", default="true", show_default=True,
              help="Modo headless del browser: true/false")
@click.option("--timeout", default=3, show_default=True, type=int,
              help="Segundos de espera extra para navegación y carga")
@click.option("--output", default="reports", show_default=True,
              help="Carpeta de output para reportes y archivos JSON")
@click.option("--save-plan", default=False, is_flag=True,
              help="Guardar el plan de auditoría site-wide en un JSON adicional")
@click.option("--auth", default=None,
              help="Path al JSON de config de auth para auditar sitios con login")
def audit(url: str, spec: str | None, headless: str, timeout: int,
          output: str, save_plan: bool, auth: str | None) -> None:
    """Ejecuta la auditoría site-wide y genera un reporte estructurado por journey."""
    headless_bool = headless.lower() not in ("false", "0", "no")

    session_file: str | None = None
    if auth:
        try:
            auth_config = json.loads(Path(auth).read_text(encoding="utf-8"))
            session_file = auth_config.get("session_file")
            if session_file and not Path(session_file).exists():
                click.echo(f"  [WARN] Sesion no encontrada: {session_file}", err=True)
                click.echo("  Ejecuta primero: python site_main.py auth-only --auth " + auth, err=True)
                sys.exit(1)
        except FileNotFoundError:
            click.echo(f"  [ERROR] Config de auth no encontrada: {auth}", err=True)
            sys.exit(1)

    click.echo(f"\n  Iniciando auditoria site-wide para: {url}")
    click.echo(f"  Spec        : {spec or 'ninguna'}")
    click.echo(f"  Headless    : {headless_bool}")
    click.echo(f"  Timeout     : {timeout}s")
    click.echo(f"  Auth        : {session_file or 'ninguna'}")
    click.echo(f"  Output dir  : {output}\n")

    auditor = MultiPageAuditor(root_url=url, output_dir=output, timeout=timeout,
                               headless=headless_bool, session_file=session_file)
    try:
        plan = asyncio.run(auditor.discover_and_plan(spec_file=spec))
    except Exception as exc:
        click.echo(f"\n  [ERROR] Fallo descubrimiento o clasificacion: {exc}", err=True)
        sys.exit(1)

    if save_plan:
        plan_path = auditor.save(plan, "site_audit_plan.json")
        click.echo(f"  Plan guardado en: {plan_path}")

    click.echo(f"  URLs descubiertas: {len(plan.get('journeys', []))} journeys planificados\n")

    try:
        results = asyncio.run(auditor.run_plan(plan))
    except Exception as exc:
        click.echo(f"\n  [ERROR] Fallo ejecucion de journeys: {exc}", err=True)
        sys.exit(1)

    output_path = auditor.save(results, "site_audit_results.json")

    click.echo("  " + "-" * 56)
    click.echo(f"  Auditoria completada: {output_path}")
    click.echo(f"  Journeys ejecutados: {len(results.get('journeys', []))}")
    if results.get("errors"):
        click.echo(f"  Errores detectados en {len(results['errors'])} journey(s)")
        for error in results["errors"]:
            click.echo(f"    - {error.get('journey_id')}: {error.get('error')}")
    click.echo("  " + "-" * 56 + "\n")


# ─── Comando: auth-only ───────────────────────────────────────────────────────

@cli.command("auth-only")
@click.option("--auth", required=True, help="Path al JSON de configuracion de auth")
@click.option(
    "--notification",
    default="terminal",
    show_default=True,
    type=click.Choice(["terminal", "desktop", "webhook"]),
    help="Modo de notificacion al auditor",
)
def auth_only(auth: str, notification: str) -> None:
    """Autentica en el sitio y guarda la sesion sin ejecutar auditoria."""
    asyncio.run(_do_auth_only(auth, notification))


async def _do_auth_only(auth_config_path: str, notification_mode: str) -> None:
    from playwright.async_api import async_playwright

    from auth.session_manager import AuthenticationError, SessionManager

    config_path = Path(auth_config_path)
    if not config_path.exists():
        click.echo(f"  [ERROR] Archivo de config no encontrado: {auth_config_path}", err=True)
        sys.exit(1)

    config: dict = json.loads(config_path.read_text(encoding="utf-8"))
    config["notification_mode"] = notification_mode
    config["may_require_interaction"] = True

    domain = config.get("domain") or config.get("login_url", "")
    click.echo(f"\n  Iniciando sesion autenticada en {domain}")

    creds_env = config.get("credentials_env", {})
    user_var = creds_env.get("username", "AUDIT_USER")
    pass_var = creds_env.get("password", "AUDIT_PASS")
    if os.environ.get(user_var) and os.environ.get(pass_var):
        click.echo("  Credenciales cargadas desde variables de entorno")

    click.echo("  Abriendo browser...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            manager = SessionManager(config)
            context = await manager.get_context(browser)

            session_file = config.get("session_file", "auth/sessions/session.json")
            ttl_hours = config.get("session_ttl_hours", 8)

            click.echo(f"  Login exitoso")
            click.echo(f"  Sesion guardada: {session_file}")
            click.echo(f"  Valida por {ttl_hours} horas\n")

            await context.close()
        except AuthenticationError as exc:
            click.echo(f"\n  [ERROR] {exc}", err=True)
            sys.exit(1)
        finally:
            await browser.close()


# ─── Comando: assisted ───────────────────────────────────────────────────────

@cli.command("assisted")
@click.option("--url", required=True, help="URL de inicio (home o cualquier página)")
@click.option("--auth", default=None,
              help="Path al JSON de config de auth para cargar sesión guardada")
@click.option("--output", default="reports", show_default=True,
              help="Carpeta de output para el reporte")
@click.option("--save-session", default=None,
              help="Guardar la sesión al terminar en este path (override del session_file del auth config)")
def assisted(url: str, auth: str | None, output: str, save_session: str | None) -> None:
    """
    Abre el browser visible con el auditor activo — tú navegas,
    el sistema captura dataLayer + GA4 + pixels. ENTER para terminar y guardar.

    Flujo típico para sitios con login manual (modal, celular+OTP, SSO):
      1. El browser abre en la URL indicada.
      2. Tú haces login manualmente (cualquier método).
      3. Navegas las secciones que quieras auditar.
      4. Presionas ENTER — se guarda la sesión y se genera el reporte.
    """
    asyncio.run(_run_assisted(url, auth, output, save_session))


async def _run_assisted(
    url: str,
    auth: str | None,
    output: str,
    save_session: str | None,
) -> None:
    from playwright.async_api import async_playwright

    from modules.datalayer_recorder import DataLayerRecorder
    from modules.ga4_interceptor import GA4Interceptor
    from modules.gtm_inspector import GTMInspector

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    context_kwargs: dict = {"viewport": {"width": 1280, "height": 800}, "user_agent": _UA}

    # Determinar qué path de sesión usar
    session_path: str | None = save_session
    if auth:
        try:
            auth_config = json.loads(Path(auth).read_text(encoding="utf-8"))
            sf = auth_config.get("session_file", "")
            if sf and Path(sf).exists():
                context_kwargs["storage_state"] = sf
                click.echo(f"  Sesion cargada: {sf}")
                if not session_path:
                    session_path = sf  # Actualizar la misma sesión al terminar
            else:
                click.echo("  Sin sesion previa — loguea manualmente en el browser")
                if not session_path and sf:
                    session_path = sf  # Guardar aunque no exista aún
        except FileNotFoundError:
            click.echo(f"  [WARN] Config de auth no encontrada: {auth}", err=True)

    visited_urls: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        recorder = DataLayerRecorder()
        await recorder.install(page)
        interceptor = GA4Interceptor()
        interceptor.install(page)
        inspector = GTMInspector()

        # Registrar cada carga de página
        def _on_load() -> None:
            visited_urls.append({"url": page.url, "ts": time.time()})

        page.on("load", _on_load)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        # Hilo para esperar ENTER
        pressed = threading.Event()

        def _wait_enter() -> None:
            try:
                sys.stdin.readline()
            except Exception:
                pass
            pressed.set()

        threading.Thread(target=_wait_enter, daemon=True).start()

        click.echo(f"\n  Browser abierto: {url}")
        if session_path:
            click.echo(f"  Sesion se guardara en: {session_path}")
        click.echo("  Navega libremente — capturando dataLayer + GA4 + pixels en tiempo real.")
        click.echo("  Presiona ENTER en esta terminal cuando termines.\n")

        # Loop de status en tiempo real
        while not pressed.is_set():
            dl_count = len(await recorder.get_events())
            ga4_count = len(interceptor.hits)
            px_count = len(interceptor.pixel_hits)
            current = page.url[:55]
            sys.stdout.write(
                f"\r  {current:<55}  dl:{dl_count:3d}  ga4:{ga4_count:3d}  px:{px_count:2d}  [ENTER para terminar]"
            )
            sys.stdout.flush()
            await asyncio.sleep(2)

        print()
        click.echo("\n  Recolectando datos finales...")

        final_events = await recorder.get_events()
        final_state = await recorder.get_final_state()
        gtm_info = await inspector.inspect(page)
        final_url = page.url

        if session_path:
            Path(session_path).parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=session_path)
            click.echo(f"  Sesion guardada: {session_path}")

        await browser.close()

    # Generar reporte
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain = urlparse(url).netloc.replace(".", "_")

    report = {
        "mode": "assisted",
        "start_url": url,
        "domain": urlparse(url).netloc,
        "final_url": final_url,
        "captured_at": datetime.now().isoformat(),
        "pages_visited": len(visited_urls),
        "visited_urls": visited_urls,
        "datalayer_count": len(final_events),
        "datalayer_events": final_events,
        "datalayer_final_state": final_state,
        "ga4_count": len(interceptor.hits),
        "ga4_hits": interceptor.hits,
        "measurement_ids": interceptor.get_measurement_ids(),
        "pixel_count": len(interceptor.pixel_hits),
        "pixel_hits": interceptor.pixel_hits,
        "detected_pixels": interceptor.get_detected_pixel_types(),
        "gtm_info": gtm_info,
    }

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{domain}_assisted_{ts}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"\n  {'─' * 56}")
    click.echo(f"  Reporte: {json_path}")
    click.echo(f"  Paginas visitadas : {len(visited_urls)}")
    click.echo(f"  dataLayer events  : {len(final_events)}")
    click.echo(f"  GA4 hits          : {len(interceptor.hits)}")
    click.echo(f"  Pixels detectados : {interceptor.get_detected_pixel_types()}")
    click.echo(f"  {'─' * 56}\n")


# ─── Comando: batch ──────────────────────────────────────────────────────────

@cli.command("batch")
@click.option("--urls", required=True,
              help="Archivo .txt (una URL por línea) o .csv (url,tipo,nombre)")
@click.option("--headless", default="true", show_default=True,
              help="Modo headless: true/false")
@click.option("--timeout", default=3, show_default=True, type=int,
              help="Segundos de espera por página")
@click.option("--output", default="reports", show_default=True,
              help="Carpeta de output")
@click.option("--auth", default=None,
              help="Path al JSON de config de auth (para sitios con login)")
def batch(urls: str, headless: str, timeout: int, output: str, auth: str | None) -> None:
    """
    Audita una lista de URLs desde un archivo .txt o .csv y genera reporte HTML.

    \b
    Formato .txt — una URL por línea, # para comentarios:
        https://ejemplo.com/
        https://ejemplo.com/productos
        # https://ejemplo.com/ignorada

    \b
    Formato .csv — url,tipo,nombre (tipo y nombre opcionales):
        https://ejemplo.com/,home,Home
        https://ejemplo.com/productos,product,Catálogo
        https://ejemplo.com/contacto,contact,Contacto
    """
    asyncio.run(_run_batch(
        urls,
        headless.lower() not in ("false", "0", "no"),
        timeout,
        output,
        auth,
    ))


def _parse_urls_file(filepath: str) -> list[tuple[str, str, str]]:
    """
    Lee .txt o .csv y retorna lista de (url, tipo, nombre).
    Ignora líneas en blanco y comentarios (#).
    """
    path = Path(filepath)
    if not path.exists():
        click.echo(f"  [ERROR] Archivo no encontrado: {filepath}", err=True)
        sys.exit(1)

    suffix = path.suffix.lower()
    lines  = path.read_text(encoding="utf-8").splitlines()
    result: list[tuple[str, str, str]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if suffix == ".csv":
            parts    = [p.strip() for p in line.split(",")]
            url      = parts[0]
            url_type = parts[1] if len(parts) > 1 else ""
            name     = parts[2] if len(parts) > 2 else ""
        else:
            url      = line
            url_type = ""
            name     = ""

        # Normalizar URL
        if not url.startswith("http"):
            url = f"https://{url}"

        if not url_type:
            url_type = _infer_type(url)
        if not name:
            name = re.sub(r"https?://[^/]+", "", url) or "/"

        result.append((url, url_type, name))

    return result


def _infer_type(url: str) -> str:
    path = urlparse(url).path.lower()
    if path in ("/", ""):
        return "home"
    for kw in ("/product", "/producto", "/item", "/tienda", "/shop"):
        if kw in path:
            return "product"
    for kw in ("/contact", "/contacto"):
        if kw in path:
            return "contact"
    for kw in ("/cart", "/carrito", "/checkout", "/pago"):
        if kw in path:
            return "checkout"
    for kw in ("/blog", "/news", "/noticias", "/articul", "/post"):
        if kw in path:
            return "blog"
    for kw in ("/about", "/nosotros", "/empresa", "/quienes"):
        if kw in path:
            return "about"
    return "page"


async def _run_batch(
    urls_file: str,
    headless: bool,
    timeout: int,
    output: str,
    auth: str | None,
) -> None:
    from runners.static_runner import StaticRunner
    from modules.site_audit_report import generate_site_audit_html

    entries = _parse_urls_file(urls_file)
    if not entries:
        click.echo("  [ERROR] Ninguna URL válida encontrada en el archivo", err=True)
        sys.exit(1)

    click.echo(f"\n  {len(entries)} URLs cargadas desde {urls_file}")

    # Auth
    session_file: str | None = None
    if auth:
        try:
            auth_config = json.loads(Path(auth).read_text(encoding="utf-8"))
            sf = auth_config.get("session_file", "")
            if sf and Path(sf).exists():
                session_file = sf
                click.echo(f"  Sesion activa: {sf}")
            else:
                click.echo("  Sin sesion previa — auditando sin autenticacion")
        except FileNotFoundError:
            click.echo(f"  [WARN] Config de auth no encontrada: {auth}", err=True)

    # Construir journey único con todos los pasos
    journey = {
        "id": "batch",
        "name": f"Batch — {Path(urls_file).name}",
        "steps": [
            {"step": i + 1, "url": url, "type": url_type, "actions": ["scroll_full"]}
            for i, (url, url_type, _name) in enumerate(entries)
        ],
    }

    click.echo(f"  Ejecutando... (puede tardar {len(entries) * (timeout + 3)}s aprox.)\n")

    runner = StaticRunner(headless=headless, timeout=timeout, session_file=session_file)
    journey_result = await runner.run_journey(journey)

    # Enriquecer steps con el nombre legible del CSV/TXT
    for step_result, (_url, _type, name) in zip(
        journey_result.get("steps", []), entries
    ):
        step_result["_name"] = name

    # Estructura compatible con site_audit_results.json
    domain = urlparse(entries[0][0]).netloc if entries else "batch"
    data = {
        "mode": "batch",
        "source_file": urls_file,
        "domain": domain,
        "discovered_at": datetime.now().isoformat(),
        "spec_file": "",
        "journeys": [journey_result],
        "errors": [],
    }

    # Guardar JSON
    out_dir   = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug       = re.sub(r"[^\w]", "_", domain)[:40]
    json_path  = out_dir / f"{slug}_batch_{ts}.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generar HTML
    html_path = generate_site_audit_html(data, output)

    click.echo(f"  {'─'*56}")
    click.echo(f"  URLs auditadas : {len(journey_result.get('steps', []))}")
    click.echo(f"  dataLayer total: {len(journey_result.get('datalayer_events', []))}")
    click.echo(f"  GA4 hits total : {len(journey_result.get('ga4_hits', []))}")
    click.echo(f"  JSON           : {json_path}")
    click.echo(f"  Reporte HTML   : {html_path}")
    click.echo(f"  {'─'*56}\n")


# ─── Comando: tag-plan ───────────────────────────────────────────────────────

@cli.command("tag-plan")
@click.option("--url", default=None, help="URL raíz para crawl automático")
@click.option("--urls-file", default=None,
              help="Archivo .txt o .csv con URLs específicas a analizar (una por línea)")
@click.option("--pages", default=10, show_default=True, type=int,
              help="Número máximo de páginas (solo con --url)")
@click.option("--model", default="claude-opus-4-7", show_default=True,
              type=click.Choice(["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]),
              help="Modelo Claude para el análisis")
@click.option("--headless", default="true", show_default=True,
              help="Modo headless del browser: true/false")
@click.option("--output", default="reports", show_default=True,
              help="Carpeta de output")
@click.option("--auth", default=None,
              help="Path al JSON de config de auth (para sitios con login)")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Saltar confirmación de costo y ejecutar directamente")
@click.option("--api-key", default=None, envvar="ANTHROPIC_API_KEY",
              help="API key de Anthropic (o variable ANTHROPIC_API_KEY)")
def tag_plan(
    url: str | None, urls_file: str | None, pages: int, model: str, headless: str,
    output: str, auth: str | None, yes: bool, api_key: str | None,
) -> None:
    """
    Identifica oportunidades de tagging GA4/GTM con análisis IA.

    \b
    Dos modos:
      --url https://sitio.com        Crawl automático (hasta --pages páginas)
      --urls-file mis_urls.txt       Lista explícita de URLs (.txt o .csv)

    Flujo:
      1. Visita las páginas y extrae elementos interactivos
      2. Estima el costo de tokens ANTES de llamar a la API
      3. Pide confirmación (saltar con --yes)
      4. Analiza cada página con Claude → backlog priorizado
      5. Genera reporte HTML con matriz esfuerzo/valor

    Requiere: ANTHROPIC_API_KEY en el entorno o --api-key
    """
    if not url and not urls_file:
        click.echo("  [ERROR] Se requiere --url o --urls-file.", err=True)
        sys.exit(1)
    if not api_key:
        click.echo("  [ERROR] Se requiere ANTHROPIC_API_KEY. Exporta la variable o usa --api-key.", err=True)
        sys.exit(1)

    asyncio.run(_run_tag_plan(
        url, urls_file, pages,
        model, headless.lower() not in ("false", "0", "no"),
        output, auth, yes, api_key,
    ))


async def _run_tag_plan(
    url: str | None, urls_file: str | None, max_pages: int,
    model: str, headless: bool,
    output: str, auth: str | None, skip_confirm: bool, api_key: str,
) -> None:
    import anthropic as _anthropic
    from tagging_planner import (
        crawl_pages, visit_url_list, count_tokens_for_pages, analyze_page,
        MODEL_LABELS, MODEL_PRICING,
    )
    from modules.tagging_report import generate_tagging_report

    session_file: str | None = None
    if auth:
        try:
            auth_cfg = json.loads(Path(auth).read_text(encoding="utf-8"))
            sf = auth_cfg.get("session_file", "")
            if sf and Path(sf).exists():
                session_file = sf
                click.echo(f"  Sesion activa: {sf}")
        except FileNotFoundError:
            click.echo(f"  [WARN] Config de auth no encontrada: {auth}", err=True)

    def _progress(current: int, total: int, page_url: str) -> None:
        path = re.sub(r"https?://[^/]+", "", page_url) or "/"
        label = page_url if not path or path == "/" else path
        click.echo(f"  [{current:2d}/{total}] {label[:72]}")

    # ── Fase 1: Recolección de páginas ────────────────────────────────────────
    if urls_file:
        # Lista explícita desde archivo
        entries = _parse_urls_file(urls_file)
        if not entries:
            click.echo(f"  [ERROR] Sin URLs válidas en {urls_file}", err=True)
            sys.exit(1)
        url_list = [u for u, _t, _n in entries]
        # Determinar dominio principal (puede haber varios)
        domains = list(dict.fromkeys(urlparse(u).netloc for u in url_list))
        base_domain = domains[0] if domains else "sitio"
        click.echo(f"\n  {len(url_list)} URLs desde {urls_file}")
        if len(domains) > 1:
            click.echo(f"  Dominios: {', '.join(domains)}\n")
        else:
            click.echo()

        try:
            pages_data = await visit_url_list(
                url_list, headless=headless,
                session_file=session_file, on_progress=_progress,
            )
        except Exception as exc:
            click.echo(f"\n  [ERROR] Visita de URLs falló: {exc}", err=True)
            sys.exit(1)
    else:
        # Crawl automático desde root URL
        click.echo(f"\n  Crawleando {url} (max {max_pages} páginas)...\n")
        base_domain = urlparse(url).netloc
        try:
            pages_data = await crawl_pages(
                url, max_pages=max_pages, headless=headless,
                session_file=session_file, on_progress=_progress,
            )
        except Exception as exc:
            click.echo(f"\n  [ERROR] Crawl falló: {exc}", err=True)
            sys.exit(1)

    if not pages_data:
        click.echo("  [ERROR] No se pudo visitar ninguna página.", err=True)
        sys.exit(1)

    click.echo(f"\n  {len(pages_data)} páginas listas para analizar.\n")

    # ── Fase 2: Estimación de costo ───────────────────────────────────────────
    client = _anthropic.Anthropic(api_key=api_key)

    click.echo("  Contando tokens (via API)...", nl=False)
    try:
        cost_info = count_tokens_for_pages(client, pages_data, model)
    except Exception as exc:
        click.echo(f"\n  [WARN] Token counting falló ({exc}), usando estimación local.")
        avg = 2000
        cost_info = {
            "total_input_tokens": avg * len(pages_data),
            "estimated_output_tokens": 450 * len(pages_data),
            "avg_input_per_page": avg,
            "pages": len(pages_data),
            "costs": {
                m: {
                    "input_usd":  avg * len(pages_data) * p["input"] / 1_000_000,
                    "output_usd": 450 * len(pages_data) * p["output"] / 1_000_000,
                    "total_usd":  (avg * len(pages_data) * p["input"] + 450 * len(pages_data) * p["output"]) / 1_000_000,
                }
                for m, p in MODEL_PRICING.items()
            },
        }
    click.echo(" listo.\n")

    click.echo("  " + "─" * 58)
    click.echo(f"  Páginas a analizar    : {cost_info['pages']}")
    click.echo(f"  Tokens input (total)  : {cost_info['total_input_tokens']:,}")
    click.echo(f"  Tokens output (est.)  : {cost_info['estimated_output_tokens']:,}")
    click.echo()
    click.echo("  Costo estimado por modelo:")
    for m_id, c in cost_info["costs"].items():
        marker = " <-- seleccionado" if m_id == model else ""
        label = MODEL_LABELS.get(m_id, m_id)
        click.echo(f"    {label:<45}  ${c['total_usd']:.4f} USD{marker}")
    click.echo("  " + "─" * 58 + "\n")

    selected_cost = cost_info["costs"][model]["total_usd"]

    if not skip_confirm:
        confirm = click.prompt(
            f"  ¿Continuar con el análisis usando {model}? [s/N]",
            default="N",
        )
        if confirm.lower() not in ("s", "si", "sí", "y", "yes"):
            click.echo("  Análisis cancelado.")
            return

    # ── Fase 3: Análisis LLM ──────────────────────────────────────────────────
    click.echo(f"\n  Analizando {len(pages_data)} páginas con {model}...\n")

    page_results = []
    for i, page_data in enumerate(pages_data, 1):
        path = re.sub(r"https?://[^/]+", "", page_data["url"]) or "/"
        click.echo(f"  [{i:2d}/{len(pages_data)}] {path[:65]}", nl=False)

        analysis = analyze_page(client, page_data, model)
        if analysis:
            opps = [o.model_dump() for o in analysis.opportunities]
            page_results.append({
                "url": page_data["url"],
                "page_type": analysis.page_type,
                "business_context": analysis.business_context,
                "opportunities": opps,
            })
            click.echo(f"  → {len(opps)} oportunidades")
        else:
            page_results.append({
                "url": page_data["url"],
                "page_type": "other",
                "business_context": "",
                "opportunities": [],
            })
            click.echo("  → sin resultados")

    # ── Fase 4: Reporte ───────────────────────────────────────────────────────
    domain = base_domain
    total_opps = sum(len(r["opportunities"]) for r in page_results)
    total_hours = sum(
        o["effort_hours"]
        for r in page_results
        for o in r["opportunities"]
    )

    html_path = generate_tagging_report(page_results, domain, model, selected_cost, output)

    # Guardar JSON con los datos crudos
    out_dir = Path(output)
    slug = re.sub(r"[^\w]", "_", domain)[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{slug}_tag_plan_{ts}.json"
    json_path.write_text(
        json.dumps({
            "domain": domain, "model": model, "cost_usd": selected_cost,
            "pages": len(page_results), "total_opportunities": total_opps,
            "total_effort_hours": total_hours, "page_results": page_results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    click.echo(f"\n  {'─' * 58}")
    click.echo(f"  Páginas analizadas    : {len(page_results)}")
    click.echo(f"  Oportunidades totales : {total_opps}")
    click.echo(f"  Esfuerzo estimado     : {total_hours:.1f}h ({total_hours/8:.1f} días)")
    click.echo(f"  Costo real API        : ~${selected_cost:.4f} USD")
    click.echo(f"  Reporte HTML          : {html_path}")
    click.echo(f"  Datos JSON            : {json_path}")
    click.echo(f"  {'─' * 58}\n")


# ─── Comando: report ─────────────────────────────────────────────────────────

@cli.command("report")
@click.argument("json_path")
@click.option("--output", default=None,
              help="Carpeta de output (default: misma carpeta del JSON)")
def report_cmd(json_path: str, output: str | None) -> None:
    """
    Genera un reporte HTML desde un JSON de auditoría.

    Ejemplo:
      python site_main.py report reports/construyexperto_pe_assisted_20260528_151131.json
    """
    path = Path(json_path)
    if not path.exists():
        click.echo(f"  [ERROR] Archivo no encontrado: {json_path}", err=True)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    out_dir = output or str(path.parent)

    if data.get("mode") == "assisted":
        from modules.assisted_report import generate_assisted_html
        html_path = generate_assisted_html(data, out_dir)
    elif "journeys" in data:
        from modules.site_audit_report import generate_site_audit_html
        html_path = generate_site_audit_html(data, out_dir)
    else:
        click.echo("  [ERROR] Formato no reconocido (esperado: mode='assisted' o clave 'journeys')", err=True)
        sys.exit(1)

    click.echo(f"\n  Reporte generado: {html_path}\n")


if __name__ == "__main__":
    cli()
