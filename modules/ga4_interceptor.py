"""
M2 - GA4 Hit Interceptor
Captura requests de red hacia GA4, Meta Pixel, TikTok, LinkedIn y otros pixels
registrando el listener ANTES de la navegación.
"""
from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse
from typing import Any

from playwright.async_api import Page, Request


# Endpoints GA4
_GA4_ENDPOINTS = (
    "analytics.google.com/g/collect",
    "analytics.google.com/j/collect",
    "google-analytics.com/g/collect",
    "google-analytics.com/collect",
)

# Otros pixels de terceros
_PIXEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "meta": ("connect.facebook.net", "facebook.com/tr"),
    "tiktok": ("analytics.tiktok.com",),
    "linkedin": ("snap.licdn.com", "px.ads.linkedin.com"),
    "twitter": ("analytics.twitter.com", "t.co/i/adsct"),
    "google_ads": ("googleads.g.doubleclick.net",),
}


def _parse_ga4_params(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    # Aplanar listas de un solo elemento
    flat: dict[str, Any] = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

    # Extraer event params (ep.* string, epn.* numeric)
    event_params: dict[str, Any] = {}
    user_props: dict[str, Any] = {}
    raw_clean: dict[str, Any] = {}

    for key, val in flat.items():
        if key.startswith("ep."):
            event_params[key[3:]] = val
        elif key.startswith("epn."):
            try:
                event_params[key[4:]] = float(val)
            except (ValueError, TypeError):
                event_params[key[4:]] = val
        elif key.startswith("up."):
            user_props[key[3:]] = val
        elif key.startswith("upn."):
            try:
                user_props[key[4:]] = float(val)
            except (ValueError, TypeError):
                user_props[key[4:]] = val
        else:
            raw_clean[key] = val

    return {
        "event_name": flat.get("en", ""),
        "measurement_id": flat.get("tid", ""),
        "client_id": flat.get("cid", ""),
        "session_id": flat.get("sid", ""),
        "engagement_time": flat.get("_et", ""),
        "event_params": event_params,
        "user_properties": user_props,
        "raw": raw_clean,
    }


class GA4Interceptor:
    """Registra todos los hits de tracking que salen del browser."""

    def __init__(self) -> None:
        self._ga4_hits: list[dict[str, Any]] = []
        self._pixel_hits: list[dict[str, Any]] = []

    def install(self, page: Page) -> None:
        """Registrar listener. Llamar ANTES de page.goto()."""
        page.on("request", self._handle_request)

    def _handle_request(self, request: Request) -> None:
        url = request.url
        ts = int(time.time() * 1000)

        # GA4
        for endpoint in _GA4_ENDPOINTS:
            if endpoint in url:
                hit = _parse_ga4_params(url)
                hit["timestamp"] = ts
                hit["url"] = url
                self._ga4_hits.append(hit)
                return

        # Otros pixels
        for pixel_type, patterns in _PIXEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in url:
                    self._pixel_hits.append({
                        "timestamp": ts,
                        "type": pixel_type,
                        "url": url,
                    })
                    return

    @property
    def hits(self) -> list[dict[str, Any]]:
        return list(self._ga4_hits)

    @property
    def pixel_hits(self) -> list[dict[str, Any]]:
        return list(self._pixel_hits)

    def get_detected_pixel_types(self) -> list[str]:
        return sorted({p["type"] for p in self._pixel_hits})

    def get_measurement_ids(self) -> list[str]:
        return sorted({h["measurement_id"] for h in self._ga4_hits if h["measurement_id"]})
