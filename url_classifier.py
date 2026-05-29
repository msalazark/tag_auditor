from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright


class URLClassifier:
    LEAD_FORM_PATHS = ["/cotizar", "/quote", "/solicitar", "/contacto", "/contact", "/demo"]
    LISTING_PATHS = ["/productos", "/tienda", "/shop", "/catalog", "/category", "/categoria"]
    PRODUCT_PATHS = ["/producto/", "/product/", "/item/", "/p/"]
    CART_PATHS = ["/cart", "/carrito", "/bolsa", "/bag"]
    CHECKOUT_PATHS = ["/checkout", "/pago", "/payment", "/comprar", "/order"]
    CONFIRMATION_PATHS = ["/thank-you", "/gracias", "/confirmacion", "/order-confirmed", "/success"]
    CONTENT_PATHS = ["/blog", "/noticias", "/news", "/articulo", "/post"]
    INSTITUTIONAL_PATHS = ["/nosotros", "/about", "/quienes-somos", "/empresa", "/historia"]

    PRODUCT_REGEX = re.compile(r"/(product|item|producto)/[\w\-]+", re.I)
    LISTING_REGEX = re.compile(r"/(products?|items?|catalog|shop|tienda)(/|$)", re.I)

    def __init__(self, headless: bool = True, timeout: int = 3):
        self.headless = headless
        self.timeout = timeout

    def _normalize_path(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path.lower()

    def _type_from_path(self, url: str) -> str | None:
        parsed = urlparse(url)
        path = self._normalize_path(url)
        query = parse_qs(parsed.query)

        if path in ("/", ""):
            return "home"
        if any(fragment in path for fragment in self.LISTING_PATHS) or self.LISTING_REGEX.search(path):
            return "ecommerce_listing"
        if any(fragment in path for fragment in self.PRODUCT_PATHS) or any(
            key in query for key in ("id", "sku", "product_id")
        ) or self.PRODUCT_REGEX.search(path):
            return "ecommerce_product"
        if any(fragment in path for fragment in self.CART_PATHS):
            return "ecommerce_cart"
        if any(fragment in path for fragment in self.CHECKOUT_PATHS):
            return "ecommerce_checkout"
        if any(fragment in path for fragment in self.CONFIRMATION_PATHS):
            # If it also looks like an ecommerce confirmation, prioritize that.
            return "ecommerce_confirmation"
        if any(fragment in path for fragment in self.LEAD_FORM_PATHS):
            return "lead_landing"
        if any(fragment in path for fragment in self.CONTENT_PATHS):
            return "content"
        if any(fragment in path for fragment in self.INSTITUTIONAL_PATHS):
            return "institutional"
        if any(fragment in path for fragment in self.CONFIRMATION_PATHS):
            return "lead_thankyou"
        return None

    async def _page_has_form(self, page, url: str) -> bool:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            await asyncio.sleep(0.5)
            form = await page.query_selector("form")
            return form is not None
        except Exception:
            return False

    def _needs_form_inspection(self, url: str) -> bool:
        path = self._normalize_path(url)
        candidate = any(fragment in path for fragment in self.LEAD_FORM_PATHS)
        return candidate

    async def classify(self, url_list: dict[str, Any]) -> dict[str, Any]:
        urls = url_list.get("urls", [])
        inspect_candidates: list[dict[str, Any]] = []

        for item in urls:
            url = item.get("url", "")
            url_type = self._type_from_path(url)
            item["type"] = url_type or "other"
            if item["type"] == "other" and self._needs_form_inspection(url):
                inspect_candidates.append(item)

        if inspect_candidates:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                for item in inspect_candidates:
                    if await self._page_has_form(page, item["url"]):
                        item["type"] = "lead_landing"
                await browser.close()

        summary = dict(Counter(item.get("type", "other") for item in urls))
        url_list["summary"] = summary
        url_list["urls"] = urls
        return url_list
