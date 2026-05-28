"""
M4 - Interaction Simulator
Simula scroll progresivo, clic en primer CTA visible y foco en formulario.
Registra cuántos eventos dataLayer se disparan después de cada acción.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import Page

from .datalayer_recorder import DataLayerRecorder


class InteractionSimulator:
    def __init__(self, recorder: DataLayerRecorder) -> None:
        self._recorder = recorder
        self._actions: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers

    async def _dl_count(self) -> int:
        events = await self._recorder.get_events()
        return len(events)

    async def _log_action(
        self,
        action_type: str,
        detail: str,
        count_before: int,
    ) -> None:
        events = await self._recorder.get_events()
        triggered = events[count_before:]
        self._actions.append({
            "type": action_type,
            "detail": detail,
            "timestamp": int(time.time() * 1000),
            "datalayer_events_triggered": triggered,
        })

    # ------------------------------------------------------------------ steps

    async def _step_scroll(self, page: Page) -> None:
        for pct in (25, 50, 75, 100):
            before = await self._dl_count()
            await page.evaluate(
                f"window.scrollTo({{top: document.body.scrollHeight * {pct} / 100, behavior: 'smooth'}})"
            )
            await asyncio.sleep(0.8)
            await self._log_action("scroll", f"{pct}%", before)

    async def _step_cta_click(self, page: Page) -> None:
        selectors = ["a[href]", "button"]
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    try:
                        if not await el.is_visible():
                            continue
                        # Solo clicks dentro del viewport
                        box = await el.bounding_box()
                        if not box:
                            continue
                        before = await self._dl_count()
                        href = await el.get_attribute("href") or ""
                        text = (await el.inner_text()).strip()[:60]
                        label = text or href[:60]
                        await el.click(timeout=3000, no_wait_after=True)
                        await asyncio.sleep(0.6)
                        await self._log_action("cta_click", f"{sel}: {label}", before)
                        return  # solo primer CTA
                    except Exception:
                        continue
            except Exception:
                continue

    async def _step_form_interact(self, page: Page) -> None:
        try:
            # Volver al inicio para buscar formularios
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.3)

            forms = await page.query_selector_all("form")
            for form in forms:
                if not await form.is_visible():
                    continue

                input_types = [
                    "input:not([type=hidden]):not([type=submit]):not([type=button])"
                    ":not([type=checkbox]):not([type=radio]):not([type=reset])",
                    "textarea",
                ]
                for sel in input_types:
                    inputs = await form.query_selector_all(sel)
                    for inp in inputs[:2]:
                        try:
                            if not await inp.is_visible():
                                continue
                            before = await self._dl_count()
                            itype = await inp.get_attribute("type") or "text"
                            name = await inp.get_attribute("name") or itype
                            value = "test@example.com" if itype == "email" else "Test 123"
                            await inp.focus()
                            await asyncio.sleep(0.2)
                            await inp.fill(value)
                            await asyncio.sleep(0.3)
                            await self._log_action(
                                "form_fill", f"input[name={name}] type={itype}", before
                            )
                        except Exception:
                            continue
                return  # solo primer formulario
        except Exception:
            pass

    # ------------------------------------------------------------------ public

    async def run(self, page: Page) -> list[dict[str, Any]]:
        """Ejecuta la secuencia completa. Retorna lista de acciones registradas."""
        # 1. Esperar networkidle antes de interactuar
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        # 2. Scroll progresivo
        await self._step_scroll(page)

        # 3. Primer CTA
        await self._step_cta_click(page)

        # 4. Formulario
        await self._step_form_interact(page)

        return self._actions

    @property
    def actions(self) -> list[dict[str, Any]]:
        return list(self._actions)
