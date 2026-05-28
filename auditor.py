"""
Orquestador principal del Tag Audit Tool.
Coordina M3 → M2 → M1 → M4 → M5 → M6 en un contexto async único de Playwright.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from modules.datalayer_recorder import DataLayerRecorder
from modules.ga4_interceptor import GA4Interceptor
from modules.gtm_inspector import GTMInspector
from modules.interaction_simulator import InteractionSimulator
from modules.report_generator import ReportGenerator
from modules.spec_validator import SpecValidator


class TagAuditor:
    def __init__(
        self,
        spec_path: str = "specs/default_spec.json",
        headless: bool = True,
        timeout: int = 3,
        output_dir: str = "reports",
    ) -> None:
        self._spec_path = spec_path
        self._headless = headless
        self._timeout = timeout
        self._output_dir = output_dir

    async def run(self, url: str) -> dict[str, Any]:
        """
        Ejecuta auditoría completa sobre `url`.
        Retorna dict con todos los resultados + paths de reportes.
        """
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # M3 — instalar proxy dataLayer ANTES de cualquier navegación
            recorder = DataLayerRecorder()
            await recorder.install(page)

            # M2 — registrar interceptor de requests ANTES de navegar
            interceptor = GA4Interceptor()
            interceptor.install(page)

            # Navegar con timeout graceful
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                print(f"  [warn] goto timeout/error: {exc} — continuando con lo capturado")

            # Espera extra configurada por el usuario
            await asyncio.sleep(self._timeout)

            # M1 — inspeccionar GTM/GA4 en el DOM
            inspector = GTMInspector()
            gtm_info = await inspector.inspect(page)

            # M4 — simulación de interacciones
            simulator = InteractionSimulator(recorder)
            actions = await simulator.run(page)

            # Recopilar datos finales
            datalayer_events = await recorder.get_events()
            ga4_hits = interceptor.hits
            pixel_types = interceptor.get_detected_pixel_types()

            await browser.close()

        # M5 — validar contra spec
        validator = SpecValidator(self._spec_path)
        validation = validator.validate(datalayer_events, ga4_hits)

        # M6 — generar reportes
        generator = ReportGenerator(self._output_dir)
        html_path, json_path = generator.generate(
            url=url,
            gtm_info=gtm_info,
            ga4_hits=ga4_hits,
            pixel_types=pixel_types,
            datalayer_events=datalayer_events,
            validation=validation,
            actions=actions,
        )

        return {
            "url": url,
            "gtm_info": gtm_info,
            "ga4_hits": ga4_hits,
            "pixel_types": pixel_types,
            "datalayer_events": datalayer_events,
            "validation": validation,
            "actions": actions,
            "html_report": str(html_path),
            "json_report": str(json_path),
        }
