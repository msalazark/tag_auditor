"""
M1 - GTM Inspector
Lee window.google_tag_manager, scripts del DOM e inline scripts para detectar
container IDs (GTM-XXXXXXX), versiones y GA4 Measurement IDs (G-XXXXXXX).
"""
from __future__ import annotations

from typing import Any

from playwright.async_api import Page


_INSPECT_SCRIPT = """
(function () {
    var result = {
        containers: [],
        gtm_ids: [],
        ga4_ids: [],
        has_gtm_object: false
    };

    // --- 1. window.google_tag_manager ---
    try {
        var gtm = window.google_tag_manager;
        if (gtm && typeof gtm === 'object') {
            result.has_gtm_object = true;
            Object.keys(gtm).forEach(function (key) {
                if (!key || key === 'loaded') return;
                var entry = { id: key, version: null, source: 'gtm_object' };
                try {
                    var c = gtm[key];
                    if (c && c.dataLayer && c.dataLayer.gtmVersion) {
                        entry.version = c.dataLayer.gtmVersion;
                    }
                } catch (e) {}
                result.containers.push(entry);
                if (key.startsWith('GTM-')) result.gtm_ids.push(key);
                if (key.startsWith('G-')) result.ga4_ids.push(key);
            });
        }
    } catch (e) {}

    // --- 2. dataLayer — buscar G-IDs en valores ---
    try {
        (window.dataLayer || []).forEach(function (item) {
            try {
                var str = JSON.stringify(item);
                var matches = str.match(/G-[A-Z0-9]{8,12}/g) || [];
                matches.forEach(function (m) {
                    if (result.ga4_ids.indexOf(m) === -1) result.ga4_ids.push(m);
                });
            } catch (e) {}
        });
    } catch (e) {}

    // --- 3. Scripts externos con src ---
    try {
        document.querySelectorAll('script[src]').forEach(function (s) {
            var src = s.getAttribute('src') || '';
            // GTM snippet: googletagmanager.com/gtm.js?id=GTM-XXX
            var gtmM = src.match(/GTM-[A-Z0-9]+/);
            if (gtmM) {
                if (result.gtm_ids.indexOf(gtmM[0]) === -1) {
                    result.gtm_ids.push(gtmM[0]);
                    result.containers.push({ id: gtmM[0], version: null, source: 'script_src' });
                }
            }
            // gtag.js: ?id=G-XXXXXXXX
            var gM = src.match(/[?&]id=(G-[A-Z0-9]+)/);
            if (gM && result.ga4_ids.indexOf(gM[1]) === -1) {
                result.ga4_ids.push(gM[1]);
            }
        });
    } catch (e) {}

    // --- 4. Inline scripts ---
    try {
        document.querySelectorAll('script:not([src])').forEach(function (s) {
            var txt = s.textContent || '';
            var gtmMs = txt.match(/GTM-[A-Z0-9]+/g) || [];
            gtmMs.forEach(function (m) {
                if (result.gtm_ids.indexOf(m) === -1) {
                    result.gtm_ids.push(m);
                    result.containers.push({ id: m, version: null, source: 'inline_script' });
                }
            });
            var gMs = txt.match(/G-[A-Z0-9]{8,12}/g) || [];
            gMs.forEach(function (m) {
                if (result.ga4_ids.indexOf(m) === -1) result.ga4_ids.push(m);
            });
        });
    } catch (e) {}

    // Deduplicar containers por ID
    var seen = {};
    result.containers = result.containers.filter(function (c) {
        if (seen[c.id]) return false;
        seen[c.id] = true;
        return true;
    });

    return result;
})()
"""


class GTMInspector:
    """Inspecciona el DOM y el runtime para detectar GTM y GA4."""

    async def inspect(self, page: Page) -> dict[str, Any]:
        """
        Retorna dict con:
          - containers: [{id, version, source}]
          - gtm_ids: [str]
          - ga4_ids: [str]
          - has_gtm_object: bool
        """
        try:
            return await page.evaluate(_INSPECT_SCRIPT)
        except Exception as exc:
            return {
                "containers": [],
                "gtm_ids": [],
                "ga4_ids": [],
                "has_gtm_object": False,
                "error": str(exc),
            }
