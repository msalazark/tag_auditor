"""
M2 - GA4 Hit Interceptor v2
Intercepta requests de red hacia GA4 y pixels de terceros antes de navegar.
Agrega deteccion de Hotjar y Microsoft Clarity.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page, Request


_GA4_ENDPOINTS = (
    "analytics.google.com/g/collect",
    "analytics.google.com/j/collect",
    "google-analytics.com/g/collect",
    "google-analytics.com/collect",
)

_PIXEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "meta":        ("connect.facebook.net", "facebook.com/tr"),
    "tiktok":      ("analytics.tiktok.com",),
    "linkedin":    ("snap.licdn.com", "px.ads.linkedin.com"),
    "twitter":     ("analytics.twitter.com", "t.co/i/adsct"),
    "hotjar":      ("static.hotjar.com", "script.hotjar.com"),
    "clarity":     ("clarity.ms", "www.clarity.ms"),
    "google_ads":  ("googleads.g.doubleclick.net", "pagead2.googlesyndication.com"),
}


def _parse_ga4(url: str) -> dict[str, Any]:
    """Parsea todos los parametros de un hit GA4."""
    params = parse_qs(urlparse(url).query)
    flat: dict[str, Any] = {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    event_params: dict[str, Any] = {}
    user_props: dict[str, Any] = {}
    raw: dict[str, Any] = {}

    for k, v in flat.items():
        if k.startswith("ep."):
            event_params[k[3:]] = v
        elif k.startswith("epn."):
            try:
                event_params[k[4:]] = float(v)
            except (ValueError, TypeError):
                event_params[k[4:]] = v
        elif k.startswith("up."):
            user_props[k[3:]] = v
        elif k.startswith("upn."):
            try:
                user_props[k[4:]] = float(v)
            except (ValueError, TypeError):
                user_props[k[4:]] = v
        else:
            raw[k] = v

    return {
        "event_name":     flat.get("en", ""),
        "measurement_id": flat.get("tid", ""),
        "client_id":      flat.get("cid", ""),
        "session_id":     flat.get("sid", ""),
        "event_params":   event_params,
        "user_properties": user_props,
        "raw":            raw,
    }


class GA4Interceptor:
    """Registra hits GA4 y detecciones de pixels de terceros."""

    def __init__(self) -> None:
        self._ga4_hits: list[dict[str, Any]] = []
        self._pixel_hits: list[dict[str, Any]] = []

    def install(self, page: Page) -> None:
        """Registrar listener ANTES de page.goto()."""
        page.on("request", self._on_request)

    def _on_request(self, request: Request) -> None:
        url = request.url
        ts = int(time.time() * 1000)

        for endpoint in _GA4_ENDPOINTS:
            if endpoint in url:
                hit = _parse_ga4(url)
                hit["timestamp"] = ts
                hit["url"] = url
                self._ga4_hits.append(hit)
                return

        for pixel_type, patterns in _PIXEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in url:
                    self._pixel_hits.append({"timestamp": ts, "type": pixel_type, "url": url})
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
        return sorted({h["measurement_id"] for h in self._ga4_hits if h.get("measurement_id")})
