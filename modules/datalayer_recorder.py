"""
M3 - dataLayer Recorder
Inyecta un proxy sobre window.dataLayer.push ANTES de que GTM cargue,
capturando cada push con timestamp, event name y parámetros completos.
"""
from __future__ import annotations

from typing import Any

from playwright.async_api import Page


# Script inyectado vía add_init_script — corre antes de cualquier otro script
_PROXY_SCRIPT = """
(function () {
    if (window.__dl_recorder_installed__) return;
    window.__dl_recorder_installed__ = true;
    window.__dl_captures__ = [];

    function intercept(item) {
        try {
            window.__dl_captures__.push({
                index: window.__dl_captures__.length,
                timestamp: Date.now(),
                data: JSON.parse(JSON.stringify(item))
            });
        } catch (e) {}
    }

    function makePush(origPush, target) {
        return function () {
            for (var i = 0; i < arguments.length; i++) {
                intercept(arguments[i]);
            }
            return origPush.apply(target, arguments);
        };
    }

    // Parchear el array actual si ya existe
    if (Array.isArray(window.dataLayer)) {
        window.dataLayer.push = makePush(Array.prototype.push, window.dataLayer);
    }

    // Interceptar cualquier asignación futura de window.dataLayer
    var _dl = window.dataLayer || [];
    if (!Array.isArray(_dl)) _dl = [];
    _dl.push = makePush(Array.prototype.push, _dl);

    Object.defineProperty(window, 'dataLayer', {
        configurable: true,
        get: function () { return _dl; },
        set: function (val) {
            _dl = val;
            if (_dl && typeof _dl === 'object') {
                _dl.push = makePush(Array.prototype.push, _dl);
            }
        }
    });
})();
"""


class DataLayerRecorder:
    """Instala el proxy y recupera eventos capturados."""

    def __init__(self) -> None:
        self._page: Page | None = None

    async def install(self, page: Page) -> None:
        """Llama antes de page.goto() para garantizar inyección temprana."""
        self._page = page
        await page.add_init_script(_PROXY_SCRIPT)

    async def get_events(self) -> list[dict[str, Any]]:
        """Retorna todos los pushes capturados hasta el momento."""
        if not self._page:
            return []
        try:
            return await self._page.evaluate("window.__dl_captures__ || []")
        except Exception:
            return []

    async def get_final_state(self) -> list[dict[str, Any]]:
        """Lee el estado completo de window.dataLayer al terminar la sesión."""
        if not self._page:
            return []
        try:
            return await self._page.evaluate(
                "(function(){ try { return JSON.parse(JSON.stringify(window.dataLayer||[])); } catch(e){ return []; } })()"
            )
        except Exception:
            return []
