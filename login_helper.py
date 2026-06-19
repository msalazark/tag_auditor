"""
Login Helper — guarda la sesión autenticada para reutilizarla en auditorías.

Uso:
    python login_helper.py --url https://app.ejemplo.com/login
    python login_helper.py --url https://app.ejemplo.com/login --out sessions/cliente.json

El script abre un browser visible. El usuario hace login normalmente.
Al presionar Enter en la consola, la sesión (cookies + localStorage) se
guarda en el archivo indicado y el browser se cierra.
"""
from __future__ import annotations

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path

import click
from playwright.async_api import async_playwright


async def _capture_session(url: str, out_path: Path) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        click.echo("\n  Browser abierto. Completa el login en la ventana del navegador.")
        click.echo("  Cuando hayas iniciado sesion y estes en la pagina correcta,")
        click.echo("  presiona Enter aqui para guardar la sesion...\n")

        # Espera input del usuario sin bloquear el event loop de asyncio
        await asyncio.get_event_loop().run_in_executor(None, input)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(out_path))
        await browser.close()


@click.command()
@click.option("--url",  required=True, help="URL de login del sitio a auditar")
@click.option("--out",  default="sessions/session.json", show_default=True,
              help="Archivo donde guardar la sesion")
def main(url: str, out: str) -> None:
    """Captura una sesion autenticada para usarla en auditorias posteriores."""
    out_path = Path(out)
    click.echo(f"\n  URL     : {url}")
    click.echo(f"  Sesion  : {out_path}\n")

    asyncio.run(_capture_session(url, out_path))

    click.echo(f"\n  Sesion guardada en: {out_path}")
    click.echo("  Usa --session con main.py para auditar paginas protegidas.\n")


if __name__ == "__main__":
    main()
