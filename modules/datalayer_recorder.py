"""
M3 - dataLayer Recorder v2
Usa un Proxy de JavaScript para interceptar window.dataLayer.push() antes de que
cualquier otro script (GTM incluido) cargue en la pagina.
"""
from __future__ import annotations

from typing import Any

from playwright.async_api import Page


# Inyectado via add_init_script — corre en cada frame antes de cualquier script
_PROXY_SCRIPT = """
(function () {
    if (window.__dl_recorder_v2__) return;
    window.__dl_recorder_v2__ = true;

    window._auditLog = [];
    const _origPush = Array.prototype.push;

    function makeProxy(arr) {
        return new Proxy(arr, {
            get(target, prop, receiver) {
                if (prop === 'push') {
                    return function (...args) {
                        for (const arg of args) {
                            try {
                                window._auditLog.push({
                                    ts: Date.now(),
                                    index: target.length,
                                    payload: JSON.parse(JSON.stringify(arg))
                                });
                            } catch (e) {}
                        }
                        return _origPush.apply(target, args);
                    };
                }
                const val = Reflect.get(target, prop, receiver);
                return typeof val === 'function' ? val.bind(target) : val;
            },
            set(target, prop, value, receiver) {
                return Reflect.set(target, prop, value, receiver);
            }
        });
    }

    // Copiar items previos si dataLayer ya existe
    const _initial = Array.isArray(window.dataLayer)
        ? [...window.dataLayer]
        : [];
    const _arr = [];
    const _proxy = makeProxy(_arr);

    // Replay items anteriores para que queden en _auditLog
    for (const item of _initial) {
        try {
            window._auditLog.push({
                ts: Date.now(),
                index: _arr.length,
                payload: JSON.parse(JSON.stringify(item))
            });
        } catch (e) {}
        _origPush.call(_arr, item);
    }

    Object.defineProperty(window, 'dataLayer', {
        configurable: true,
        enumerable: true,
        get: () => _proxy,
        set: (newVal) => {
            // Si alguien re-asigna dataLayer (ej. window.dataLayer = window.dataLayer || [])
            // ignoramos la asignacion y seguimos devolviendo el proxy.
            // Si trae items nuevos los incorporamos.
            if (Array.isArray(newVal) && newVal !== _proxy) {
                newVal.forEach(item => {
                    if (!_arr.includes(item)) {
                        try {
                            window._auditLog.push({
                                ts: Date.now(),
                                index: _arr.length,
                                payload: JSON.parse(JSON.stringify(item))
                            });
                        } catch (e) {}
                        _origPush.call(_arr, item);
                    }
                });
            }
        }
    });
})();
"""


class DataLayerRecorder:
    """Instala el proxy y recupera el log de eventos capturados."""

    def __init__(self) -> None:
        self._page: Page | None = None

    async def install(self, page: Page) -> None:
        """Llamar antes de page.goto(). El script corre antes que GTM."""
        self._page = page
        await page.add_init_script(_PROXY_SCRIPT)

    async def get_events(self) -> list[dict[str, Any]]:
        """Retorna todos los pushes capturados hasta el momento."""
        if not self._page:
            return []
        try:
            return await self._page.evaluate("window._auditLog || []")
        except Exception:
            return []

    async def get_final_state(self) -> list[dict[str, Any]]:
        """Lee el estado completo de window.dataLayer al terminar la sesion."""
        if not self._page:
            return []
        try:
            return await self._page.evaluate(
                "(function(){try{return JSON.parse(JSON.stringify(window.dataLayer||[]));}catch(e){return [];}})()"
            )
        except Exception:
            return []
