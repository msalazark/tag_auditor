"""
Orquestador principal v2.
Carga y valida la spec del usuario contra spec_schema.json antes de auditar.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import jsonschema
from playwright.async_api import async_playwright

from modules.datalayer_recorder import DataLayerRecorder
from modules.ga4_interceptor import GA4Interceptor
from modules.gtm_inspector import GTMInspector
from modules.interaction_simulator import InteractionSimulator
from modules.report_generator import ReportGenerator
from modules.spec_validator import SpecValidator

_SCHEMA_PATH = Path(__file__).parent / "specs" / "spec_schema.json"


class SpecError(ValueError):
    """La spec del usuario no cumple el schema."""


class TagAuditor:
    def __init__(
        self,
        spec_path: str,
        headless: bool = True,
        timeout: int = 3,
        output_dir: str = "reports",
    ) -> None:
        self._spec_path  = spec_path
        self._headless   = headless
        self._timeout    = timeout
        self._output_dir = output_dir

    # ── carga y validacion de spec ────────────────────────────────────────────

    def load_spec(self) -> dict[str, Any]:
        path = Path(self._spec_path)
        try:
            with open(path, encoding="utf-8") as f:
                spec = json.load(f)
        except FileNotFoundError:
            raise SpecError(f"Archivo de spec no encontrado: {path}")
        except json.JSONDecodeError as exc:
            raise SpecError(f"JSON invalido en {path}: {exc}")

        # Validar contra spec_schema.json
        try:
            schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
            jsonschema.validate(instance=spec, schema=schema)
        except jsonschema.ValidationError as exc:
            raise SpecError(f"Spec no cumple el schema: {exc.message} (path: {list(exc.path)})")

        spec["_filename"] = path.name
        return spec

    # ── auditoria principal ───────────────────────────────────────────────────

    async def run(self, url: str) -> dict[str, Any]:
        spec = self.load_spec()

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

            # M3 — proxy dataLayer ANTES de cualquier script
            recorder = DataLayerRecorder()
            await recorder.install(page)

            # M2 — interceptor de requests ANTES de navegar
            interceptor = GA4Interceptor()
            interceptor.install(page)

            # Navegar con timeout graceful
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                print(f"  [warn] navegacion: {exc} -- continuando con lo capturado")

            await asyncio.sleep(self._timeout)

            # M1 — inspeccion del DOM
            inspector = GTMInspector()
            gtm_info = await inspector.inspect(page)

            # M4 — simulacion de interacciones
            simulator = InteractionSimulator(recorder)
            actions = await simulator.run(page)

            dl_events   = await recorder.get_events()
            ga4_hits    = interceptor.hits
            pixel_types = interceptor.get_detected_pixel_types()

            await browser.close()

        # M5 — validacion contra spec
        validator  = SpecValidator(spec)
        validation = validator.validate(dl_events, ga4_hits)

        # M6 — generacion de reportes
        generator = ReportGenerator(self._output_dir)
        html_path, json_path = generator.generate(
            url=url,
            spec_meta=spec,
            gtm_info=gtm_info,
            ga4_hits=ga4_hits,
            pixel_types=pixel_types,
            dl_events=dl_events,
            validation=validation,
            actions=actions,
        )

        return {
            "url":            url,
            "spec":           spec,
            "gtm_info":       gtm_info,
            "ga4_hits":       ga4_hits,
            "pixel_types":    pixel_types,
            "dl_events":      dl_events,
            "validation":     validation,
            "actions":        actions,
            "html_report":    str(html_path),
            "json_report":    str(json_path),
        }
