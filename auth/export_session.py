"""
Exportación manual de sesiones desde un browser Playwright.
Útil cuando el flow de login es demasiado complejo para automatizar.

Uso:
    python auth/export_session.py <url> [session_file]

    Ejemplo:
    python auth/export_session.py https://app.lapositiva.com.pe auth/sessions/lapositiva.json
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

from playwright.async_api import async_playwright


async def export_session_interactive(
    url: str,
    session_file: str = "auth/sessions/manual_session.json",
    timeout_minutes: int = 10,
) -> Path:
    """
    Abre un browser visible, permite el login manual y guarda la sesión.
    Retorna el path donde quedó guardado el storage state.
    """
    session_path = Path(session_file)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  Abriendo browser en: {url}")
    print(f"  Tienes {timeout_minutes} minutos para completar el login.")
    print("  Cuando termines, presiona ENTER en esta terminal.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto(url)

        pressed = threading.Event()

        def _wait_enter() -> None:
            try:
                sys.stdin.readline()
            except Exception:
                pass
            pressed.set()

        t = threading.Thread(target=_wait_enter, daemon=True)
        t.start()

        timeout_secs = timeout_minutes * 60
        start = time.time()

        while time.time() - start < timeout_secs and not pressed.is_set():
            remaining = int(timeout_secs - (time.time() - start))
            sys.stdout.write(f"\r  Esperando login manual... {remaining}s (ENTER para guardar) ")
            sys.stdout.flush()
            await asyncio.sleep(1)

        print()

        if not pressed.is_set():
            print(f"  Timeout ({timeout_minutes} min). Sesion no guardada.")
            await browser.close()
            return session_path

        await context.storage_state(path=str(session_path))
        await browser.close()

    print(f"\n  Sesion guardada: {session_path}")
    return session_path


if __name__ == "__main__":
    _url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    _output = sys.argv[2] if len(sys.argv) > 2 else "auth/sessions/manual_session.json"
    _minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    asyncio.run(export_session_interactive(_url, _output, _minutes))
