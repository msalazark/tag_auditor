from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import async_playwright, ElementHandle, Page

from modules.datalayer_recorder import DataLayerRecorder
from modules.ga4_interceptor import GA4Interceptor
from modules.gtm_inspector import GTMInspector


class EcommerceRunner:
    FIRST_PRODUCT_SELECTORS = [
        ".product-item a",
        ".product-card a",
        "[class*=product] a",
        "article a",
    ]
    ADD_TO_CART_SELECTORS = [
        "button[class*=cart]",
        "button[class*=add]",
        "[data-action*=cart]",
        "button:has-text(\"Agregar\")",
        "button:has-text(\"Añadir\")",
        "button:has-text(\"Add to cart\")",
    ]
    CHECKOUT_SELECTORS = [
        "button:has-text(\"Checkout\")",
        "button:has-text(\"Pagar\")",
        "a[href*=checkout]",
        "a[href*=pago]",
    ]

    def __init__(self, headless: bool = True, timeout: int = 3, session_file: str | None = None):
        self.headless = headless
        self.timeout = timeout
        self.session_file = session_file

    async def _click_first_match(self, page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                if not await el.is_visible():
                    continue
                try:
                    await el.click(timeout=5000, no_wait_after=True)
                    await asyncio.sleep(1.0)
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

        if "click_first_product" in step.get("actions", []):
            await self._click_first_match(page, self.FIRST_PRODUCT_SELECTORS)
        if "click_add_to_cart" in step.get("actions", []):
            await self._click_first_match(page, self.ADD_TO_CART_SELECTORS)
        if "click_checkout" in step.get("actions", []):
            await self._click_first_match(page, self.CHECKOUT_SELECTORS)

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
