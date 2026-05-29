from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import async_playwright, Page

from modules.datalayer_recorder import DataLayerRecorder
from modules.ga4_interceptor import GA4Interceptor
from modules.gtm_inspector import GTMInspector


class StaticRunner:
    def __init__(self, headless: bool = True, timeout: int = 3, session_file: str | None = None):
        self.headless = headless
        self.timeout = timeout
        self.session_file = session_file

    async def _scroll_full(self, page: Page) -> None:
        for pct in (25, 50, 75, 100):
            try:
                await page.evaluate(
                    f"window.scrollTo({{top: document.body.scrollHeight * {pct} / 100, behavior: 'smooth'}})"
                )
            except Exception:
                return  # Contexto destruido por navegación — skip scroll
            await asyncio.sleep(1.0)
        try:
            await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        except Exception:
            pass
        await asyncio.sleep(0.5)

    async def _capture_links(self, page: Page) -> list[str]:
        try:
            anchors = await page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
            )
            return [href for href in anchors if isinstance(href, str)]
        except Exception:
            return []

    async def _run_step(self, page: Page, step: dict[str, Any], recorder: DataLayerRecorder, interceptor: GA4Interceptor) -> dict[str, Any]:
        url = step.get("url")
        current_url = page.url
        before_dl = len(await recorder.get_events())
        before_ga4 = len(interceptor.hits)

        if url and url != "infer":
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 5000)
                # Esperar carga completa antes de interactuar
                await page.wait_for_load_state("load", timeout=self.timeout * 3000)
            except Exception:
                pass

        actions = []
        if "scroll_full" in step.get("actions", []):
            await self._scroll_full(page)
            actions.append("scroll_full")
        if "capture_links" in step.get("actions", []):
            links = await self._capture_links(page)
            actions.append("capture_links")
        if page.url != current_url:
            current_url = page.url

        await asyncio.sleep(0.5)
        after_dl = len(await recorder.get_events())
        after_ga4 = len(interceptor.hits)

        return {
            "step": step.get("step"),
            "requested_url": url,
            "url": current_url,
            "type": step.get("type"),
            "actions": actions,
            "captured_links": len(links) if "links" in locals() else 0,
            "new_datalayer_events": (await recorder.get_events())[before_dl:after_dl],
            "new_ga4_hits": interceptor.hits[before_ga4:after_ga4],
            "status": "ok",
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
