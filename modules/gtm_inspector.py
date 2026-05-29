"""
M1 - GTM Inspector v2
Detecta GTM containers, GA4 IDs y scripts de terceros (Meta fbq, Hotjar hj,
Microsoft Clarity, LinkedIn, TikTok) inspeccionando el runtime y el DOM.
"""
from __future__ import annotations

from typing import Any

from playwright.async_api import Page


_INSPECT_SCRIPT = """
(function () {
    var r = {
        containers: [],
        gtm_ids: [],
        ga4_ids: [],
        has_gtm_object: false,
        third_party: {}
    };

    // 1. window.google_tag_manager
    try {
        var gtm = window.google_tag_manager;
        if (gtm && typeof gtm === 'object') {
            r.has_gtm_object = true;
            Object.keys(gtm).forEach(function (key) {
                if (!key || key === 'loaded') return;
                var entry = { id: key, version: null, source: 'gtm_object' };
                try {
                    var c = gtm[key];
                    if (c && c.dataLayer && c.dataLayer.gtmVersion) {
                        entry.version = String(c.dataLayer.gtmVersion);
                    }
                } catch (e) {}
                r.containers.push(entry);
                if (key.startsWith('GTM-')) r.gtm_ids.push(key);
                if (key.startsWith('G-'))   r.ga4_ids.push(key);
            });
        }
    } catch (e) {}

    // 2. dataLayer — buscar G-IDs
    try {
        (window.dataLayer || []).forEach(function (item) {
            try {
                var str = JSON.stringify(item);
                (str.match(/G-[A-Z0-9]{8,12}/g) || []).forEach(function (m) {
                    if (r.ga4_ids.indexOf(m) === -1) r.ga4_ids.push(m);
                });
            } catch (e) {}
        });
    } catch (e) {}

    // 3. Scripts externos
    try {
        document.querySelectorAll('script[src]').forEach(function (s) {
            var src = s.getAttribute('src') || '';
            var gtmM = src.match(/GTM-[A-Z0-9]+/);
            if (gtmM && r.gtm_ids.indexOf(gtmM[0]) === -1) {
                r.gtm_ids.push(gtmM[0]);
                r.containers.push({ id: gtmM[0], version: null, source: 'script_src' });
            }
            var gM = src.match(/[?&]id=(G-[A-Z0-9]+)/);
            if (gM && r.ga4_ids.indexOf(gM[1]) === -1) r.ga4_ids.push(gM[1]);
        });
    } catch (e) {}

    // 4. Inline scripts — GTM y G-IDs
    try {
        document.querySelectorAll('script:not([src])').forEach(function (s) {
            var txt = s.textContent || '';
            (txt.match(/GTM-[A-Z0-9]+/g) || []).forEach(function (m) {
                if (r.gtm_ids.indexOf(m) === -1) {
                    r.gtm_ids.push(m);
                    r.containers.push({ id: m, version: null, source: 'inline_script' });
                }
            });
            (txt.match(/G-[A-Z0-9]{8,12}/g) || []).forEach(function (m) {
                if (r.ga4_ids.indexOf(m) === -1) r.ga4_ids.push(m);
            });
        });
    } catch (e) {}

    // 5. Terceros — Meta fbq, Hotjar hj, Clarity, LinkedIn
    try { r.third_party.meta_pixel     = typeof window.fbq === 'function'; } catch (e) {}
    try { r.third_party.hotjar         = typeof window.hj  === 'function'; } catch (e) {}
    try { r.third_party.clarity        = typeof window.clarity === 'function'; } catch (e) {}
    try { r.third_party.linkedin       = typeof window._linkedin_data_partner_ids !== 'undefined'; } catch (e) {}
    try { r.third_party.tiktok         = typeof window.ttq !== 'undefined'; } catch (e) {}
    try { r.third_party.google_ads     = typeof window.gtag === 'function'; } catch (e) {}

    // Deduplicar containers por ID
    var seen = {};
    r.containers = r.containers.filter(function (c) {
        if (seen[c.id]) return false;
        seen[c.id] = true;
        return true;
    });

    return r;
})()
"""


class GTMInspector:
    async def inspect(self, page: Page) -> dict[str, Any]:
        """
        Retorna:
          containers: [{id, version, source}]
          gtm_ids, ga4_ids: [str]
          has_gtm_object: bool
          third_party: {meta_pixel, hotjar, clarity, linkedin, tiktok, google_ads}
        """
        try:
            return await page.evaluate(_INSPECT_SCRIPT)
        except Exception as exc:
            return {
                "containers": [], "gtm_ids": [], "ga4_ids": [],
                "has_gtm_object": False, "third_party": {}, "error": str(exc),
            }
