from __future__ import annotations

import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

from playwright.async_api import async_playwright, Page


class SiteCrawler:
    SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]
    MAX_SITEMAP_URLS = 500
    MAX_CRAWL_URLS = 100
    MAX_CRAWL_DEPTH = 3

    def __init__(self, root_url: str, output_dir: str = "reports", timeout: int = 3,
                 headless: bool = True, session_file: str | None = None):
        self.root_url = self._normalize_url(root_url)
        parsed = urlparse(self.root_url)
        self.scheme = parsed.scheme or "https"
        self.netloc = parsed.netloc
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.headless = headless
        self.session_file = session_file
        self.visited_sitemaps: set[str] = set()

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if not urlparse(url).scheme:
            url = f"https://{url.lstrip('/')}"
        url, _ = urldefrag(url)
        return url.rstrip("/") or url

    def _same_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == self.netloc

    def _fetch_text(self, url: str) -> str | None:
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=self.timeout) as response:
                return response.read().decode("utf-8", errors="ignore")
        except (HTTPError, URLError, ValueError):
            return None

    def _extract_urls_from_sitemap_xml(self, xml_text: str) -> list[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        urls: list[str] = []
        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}")[0] + "}"

        if root.tag == f"{namespace}sitemapindex":
            for sitemap in root.findall(f".//{namespace}sitemap"):
                loc = sitemap.find(f"{namespace}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
        elif root.tag == f"{namespace}urlset":
            for url_item in root.findall(f".//{namespace}url"):
                loc = url_item.find(f"{namespace}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())

        return urls

    def _resolve_sitemap_urls(self, url: str, depth: int = 0) -> list[str]:
        if depth > 5 or url in self.visited_sitemaps:
            return []
        self.visited_sitemaps.add(url)

        body = self._fetch_text(url)
        if not body:
            return []

        urls = self._extract_urls_from_sitemap_xml(body)
        resolved_urls: list[str] = []
        for item in urls:
            if len(resolved_urls) >= self.MAX_SITEMAP_URLS:
                break
            item_url = self._normalize_url(urljoin(url, item))
            resolved_urls.append(item_url)
            if item_url.lower().endswith(".xml"):
                resolved_urls.extend(self._resolve_sitemap_urls(item_url, depth + 1))
                if len(resolved_urls) >= self.MAX_SITEMAP_URLS:
                    break
        return list(dict.fromkeys(resolved_urls))[: self.MAX_SITEMAP_URLS]

    def _parse_robots_txt(self, content: str) -> tuple[list[str], list[str]]:
        sitemap_urls: list[str] = []
        disallowed: list[str] = []
        for line in content.splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text.lower().startswith("sitemap:"):
                parts = text.split(":", 1)
                if len(parts) == 2:
                    sitemap_urls.append(parts[1].strip())
            elif text.lower().startswith("disallow:"):
                parts = text.split(":", 1)
                if len(parts) == 2:
                    disallowed.append(parts[1].strip())
        return sitemap_urls, disallowed

    def _make_item(self, url: str, depth: int, source: str) -> dict[str, Any]:
        parsed = urlparse(url)
        return {
            "url": url,
            "path": parsed.path or "/",
            "depth": depth,
            "discovered_from": source,
            "allowed": True,
        }

    def _filter_anchor(self, href: str) -> str | None:
        if not href:
            return None
        href = href.strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            return None
        if href.lower().endswith(".pdf"):
            return None
        if href.startswith("javascript:"):
            return None
        return self._normalize_url(urljoin(self.root_url, href))

    async def _crawl_superficial(self) -> list[dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        queue: list[tuple[str, int, str]] = [(self.root_url, 0, "crawl")]

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
            while queue and len(discovered) < self.MAX_CRAWL_URLS:
                url, depth, source = queue.pop(0)
                if url in discovered or depth > self.MAX_CRAWL_DEPTH:
                    continue
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    # Esperar networkidle para SPAs que renderizan links con JS
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception:
                        pass
                    await asyncio.sleep(1.5)
                except Exception:
                    continue
                discovered[url] = self._make_item(url, depth, source)
                # Buscar tanto <a href> como rutas en atributos data- y router-link (frameworks JS)
                anchors = await page.eval_on_selector_all(
                    "a[href]",
                    "elements => elements.map(el => el.getAttribute('href'))",
                )
                for href in anchors:
                    if not href:
                        continue
                    normalized = self._filter_anchor(href)
                    if not normalized or not self._same_domain(normalized):
                        continue
                    if normalized not in discovered and len(discovered) < self.MAX_CRAWL_URLS:
                        queue.append((normalized, depth + 1, "crawl"))
            await browser.close()

        return list(discovered.values())

    async def discover(self) -> dict[str, Any]:
        url_records: list[dict[str, Any]] = []
        source = "sitemap"

        for path in self.SITEMAP_PATHS:
            candidate = self._normalize_url(urljoin(self.root_url, path))
            urls = self._resolve_sitemap_urls(candidate)
            if urls:
                source = "sitemap"
                url_records = [self._make_item(u, 0, "sitemap") for u in urls]
                break

        disallowed_paths: list[str] = []
        if not url_records:
            robots_url = self._normalize_url(urljoin(self.root_url, "/robots.txt"))
            content = self._fetch_text(robots_url)
            if content:
                sitemap_urls, disallowed_paths = self._parse_robots_txt(content)
                urls: list[str] = []
                for sitemap in sitemap_urls:
                    if len(urls) >= self.MAX_SITEMAP_URLS:
                        break
                    urls.extend(self._resolve_sitemap_urls(self._normalize_url(urljoin(self.root_url, sitemap))))
                if urls:
                    source = "robots"
                    url_records = [self._make_item(u, 0, "robots") for u in urls]

        if not url_records or len(url_records) < 10:
            crawled = await self._crawl_superficial()
            source = "crawl"
            url_records = crawled

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result = {
            "domain": self.netloc,
            "discovered_at": timestamp,
            "source": source,
            "total_urls": len(url_records),
            "disallowed_paths": disallowed_paths,
            "urls": url_records,
        }
        return result

    def save(self, data: dict[str, Any], path: str | Path) -> Path:
        output_path = Path(path)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
