"""
M4 - Interaction Simulator v2
Scroll progresivo con 1s de pausa, retorno al top, y clics en selectores
especificos (WhatsApp, tel:, PDF, CTA, formulario) sin forzar navegacion.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import Page

from .datalayer_recorder import DataLayerRecorder


# Orden de selectores a intentar clicar — solo el primero visible de cada tipo
_CTA_SELECTORS = [
    ("whatsapp", "a[href*='wa.me']"),
    ("tel",      "a[href^='tel:']"),
    ("pdf",      "a[href$='.pdf']"),
    ("submit",   "button[type='submit']"),
    ("cta",      ".cta"),
    ("contact",  "[class*='contact']"),
    ("button",   "button"),
    ("link",     "a[href]"),
]


class InteractionSimulator:
    def __init__(self, recorder: DataLayerRecorder) -> None:
        self._recorder = recorder
        self._actions: list[dict[str, Any]] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _dl_count(self) -> int:
        return len(await self._recorder.get_events())

    async def _log(self, action_type: str, detail: str, before: int) -> None:
        events = await self._recorder.get_events()
        self._actions.append({
            "type":   action_type,
            "detail": detail,
            "timestamp": int(time.time() * 1000),
            "datalayer_events_triggered": events[before:],
        })

    # ── pasos ─────────────────────────────────────────────────────────────────

    async def _step_scroll(self, page: Page) -> None:
        for pct in (25, 50, 75, 100):
            before = await self._dl_count()
            await page.evaluate(
                f"window.scrollTo({{top: document.body.scrollHeight * {pct} / 100, behavior: 'smooth'}})"
            )
            await asyncio.sleep(1.0)
            await self._log("scroll", f"{pct}%", before)

        # Volver al top
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await asyncio.sleep(0.5)

    async def _step_cta_clicks(self, page: Page) -> None:
        clicked_types: set[str] = set()

        for cta_type, selector in _CTA_SELECTORS:
            if cta_type in clicked_types:
                continue
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    try:
                        if not await el.is_visible():
                            continue
                        box = await el.bounding_box()
                        if not box:
                            continue

                        before = await self._dl_count()
                        href  = await el.get_attribute("href") or ""
                        text  = (await el.inner_text()).strip()[:60]
                        label = text or href[:60]

                        # Para links externos/tel/pdf usamos dispatchEvent para no navegar
                        if any(x in href for x in ("wa.me", "tel:", ".pdf", "http")):
                            await page.evaluate(
                                "el => el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}))",
                                el,
                            )
                        else:
                            await el.click(timeout=3000, no_wait_after=True)

                        await asyncio.sleep(0.6)
                        await self._log(f"click_{cta_type}", f"{selector}: {label}", before)
                        clicked_types.add(cta_type)
                        break
                    except Exception:
                        continue
            except Exception:
                continue

    async def _step_form(self, page: Page) -> None:
        try:
            forms = await page.query_selector_all("form")
            for form in forms:
                if not await form.is_visible():
                    continue
                inputs = await form.query_selector_all(
                    "input:not([type=hidden]):not([type=submit]):not([type=button])"
                    ":not([type=checkbox]):not([type=radio]):not([type=reset]),"
                    "textarea"
                )
                filled = 0
                for inp in inputs[:3]:
                    try:
                        if not await inp.is_visible():
                            continue
                        before = await self._dl_count()
                        itype = await inp.get_attribute("type") or "text"
                        name  = await inp.get_attribute("name") or itype
                        value = "test@ejemplo.com" if itype == "email" else "Test Auditoria"
                        await inp.focus()
                        await asyncio.sleep(0.2)
                        await inp.fill(value)
                        await asyncio.sleep(0.3)
                        await self._log("form_fill", f"input[name={name}] type={itype}", before)
                        filled += 1
                    except Exception:
                        continue
                if filled > 0:
                    return  # solo el primer formulario con inputs visibles
        except Exception:
            pass

    # ── public ────────────────────────────────────────────────────────────────

    async def run(self, page: Page) -> list[dict[str, Any]]:
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        await self._step_scroll(page)
        await self._step_cta_clicks(page)
        await self._step_form(page)
        return self._actions

    @property
    def actions(self) -> list[dict[str, Any]]:
        return list(self._actions)
