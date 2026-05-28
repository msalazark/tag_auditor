"""
M5 - Spec Validator
Cruza eventos capturados (dataLayer + hits GA4) contra el JSON de spec,
determinando estado OK / PARCIAL / AUSENTE y calculando score de cobertura.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SpecValidator:
    def __init__(self, spec_path: str) -> None:
        self._spec = self._load(spec_path)

    @staticmethod
    def _load(path: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _build_event_map(
        datalayer_events: list[dict[str, Any]],
        ga4_hits: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Agrupa todos los parámetros por nombre de evento."""
        event_map: dict[str, list[dict[str, Any]]] = {}

        for capture in datalayer_events:
            data = capture.get("data", {})
            name = data.get("event", "")
            if name:
                # Aplanar el dict completo como parámetros disponibles
                event_map.setdefault(name, []).append(data)

        for hit in ga4_hits:
            name = hit.get("event_name", "")
            if name:
                merged = {**hit.get("event_params", {}), **hit.get("raw", {})}
                event_map.setdefault(name, []).append(merged)

        return event_map

    # ------------------------------------------------------------------ public

    def validate(
        self,
        datalayer_events: list[dict[str, Any]],
        ga4_hits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Retorna:
          - results: [{event_name, trigger, priority, status, found_params, missing_params, instances_count}]
          - coverage_score: float 0-100 (solo eventos OK)
          - gaps: resultados que no son OK, ordenados P1→P3
          - ok_count, total_count
        """
        event_map = self._build_event_map(datalayer_events, ga4_hits)

        results: list[dict[str, Any]] = []
        ok_count = 0

        for spec_event in self._spec.get("events", []):
            name: str = spec_event["name"]
            required: list[str] = spec_event.get("required_params", [])
            priority: str = spec_event.get("priority", "P3")
            trigger: str = spec_event.get("trigger", "")

            instances = event_map.get(name, [])

            if not instances:
                status = "AUSENTE"
                found_params: list[str] = []
                missing_params: list[str] = list(required)
            else:
                # Tomar la instancia con más parámetros encontrados
                best_found: list[str] = []
                for inst in instances:
                    found = [p for p in required if p in inst]
                    if len(found) > len(best_found):
                        best_found = found

                found_params = best_found
                missing_params = [p for p in required if p not in found_params]

                if not missing_params:
                    status = "OK"
                    ok_count += 1
                else:
                    status = "PARCIAL"

            results.append({
                "event_name": name,
                "trigger": trigger,
                "priority": priority,
                "status": status,
                "found_params": found_params,
                "missing_params": missing_params,
                "instances_count": len(instances),
            })

        total = len(results)
        coverage_score = round(ok_count / total * 100, 1) if total else 0.0

        priority_order = {"P1": 0, "P2": 1, "P3": 2}
        gaps = sorted(
            [r for r in results if r["status"] != "OK"],
            key=lambda r: (priority_order.get(r["priority"], 9), r["event_name"]),
        )

        return {
            "results": results,
            "coverage_score": coverage_score,
            "gaps": gaps,
            "ok_count": ok_count,
            "total_count": total,
        }
