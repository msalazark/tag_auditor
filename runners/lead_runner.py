from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import async_playwright, ElementHandle, Page

from modules.datalayer_recorder import DataLayerRecorder
from modules.ga4_interceptor import GA4Interceptor
from modules.gtm_inspector import GTMInspector


class LeadRunner:
    SUBMIT_SELECTORS = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text(\"Enviar\")",
        "button:has-text(\"Cotizar\")",
        "button:has-text(\"Solicitar\")",
        "button:has-text(\"Contactar\")",
    ]

    def __init__(self, headless: bool = True, timeout: int = 3, session_file: str | None = None):
        self.headless = headless
        self.timeout = timeout
        self.session_file = session_file

    async def _fill_form_inputs(self, page: Page) -> int:
        filled = 0
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=self.timeout * 1000)
        except Exception:
            pass

        elements = await page.query_selector_all(
            "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]), textarea, select"
        )
        for el in elements:
            if not await el.is_visible():
                continue
            tag = await el.evaluate("node => node.tagName.toLowerCase()")
            itype = await el.get_attribute("type") or "text"
            try:
                if tag == "select":
                    options = await el.query_selector_all("option")
                    for option in options:
                        value = await option.get_attribute("value") or ""
                        if value.strip():
                            await el.select_option(value)
                            filled += 1
                            break
                elif tag == "textarea":
                    await el.fill("Consulta de auditoría de tagging")
                    filled += 1
                elif itype == "email":
                    await el.fill("test@auditoria.local")
                    filled += 1
                elif itype == "tel":
                    await el.fill("+51999000000")
                    filled += 1
                elif itype == "number":
                    await el.fill("1")
                    filled += 1
                else:
                    await el.fill("Juan Prueba")
                    filled += 1
                await asyncio.sleep(0.2)
            except Exception:
                continue
            if filled >= 10:
                break
        return filled

    async def _click_submit(self, page: Page) -> bool:
        for selector in self.SUBMIT_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click(timeout=5000, no_wait_after=True)
                    await asyncio.sleep(3.0)
                    return True
            except Exception:
                continue
        return False

    async def _run_step(self, page: Page, step: dict[str, Any], recorder: DataLayerRecorder, interceptor: GA4Interceptor) -> dict[str, Any]:
        url = step.get("url")
        current_url = page.url
        before_dl = len(await recorder.get_events())
        before_ga4 = len(interceptor.hits)

        if url and url != "infer":
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            except Exception:
                pass

        filled = 0
        submitted = False
        if "fill_form_inputs" in step.get("actions", []):
            filled = await self._fill_form_inputs(page)
        if "click_submit" in step.get("actions", []):
            submitted = await self._click_submit(page)

        await asyncio.sleep(1.0)
        if page.url != current_url:
            current_url = page.url

        after_dl = len(await recorder.get_events())
        after_ga4 = len(interceptor.hits)

        return {
            "step": step.get("step"),
            "requested_url": url,
            "url": current_url,
            "type": step.get("type"),
            "actions": step.get("actions", []),
            "filled_fields": filled,
            "clicked_submit": submitted,
            "status": "ok",
            "new_datalayer_events": (await recorder.get_events())[before_dl:after_dl],
            "new_ga4_hits": interceptor.hits[before_ga4:after_ga4],
        }

    async def run_journey(self, journey: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        context_kwargs: dict = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if self.session_file:
            context_kwargs["storage_state"] = self.session_file

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            recorder = DataLayerRecorder()
            await recorder.install(page)
            interceptor = GA4Interceptor()
            interceptor.install(page)
            inspector = GTMInspector()

            for step in journey.get("steps", []):
                result = await self._run_step(page, step, recorder, interceptor)
                result["gtm_info"] = await inspector.inspect(page)
                results.append(result)
            await browser.close()

        return {
            "journey_id": journey.get("id"),
            "journey_name": journey.get("name"),
            "steps": results,
            "datalayer_events": await recorder.get_events(),
            "ga4_hits": interceptor.hits,
        }
