"""
M5 - Spec Validator v2
Valida eventos capturados contra la spec del usuario con:
- Soporte de notacion de punto y bracket: ecommerce.items[0].item_id
- Verificacion de tipo de dato (string, number, boolean, array, object)
- Scores separados por categoria (ecommerce, leads, custom) y por prioridad P1
- Fuente configurable por evento: dataLayer | ga4_hit | both
"""
from __future__ import annotations

import re
from typing import Any


# ── path resolver ─────────────────────────────────────────────────────────────

def _resolve(data: Any, path: str) -> tuple[bool, Any]:
    """
    Resuelve un path como 'ecommerce.items[0].item_id' sobre un dict anidado.
    Retorna (existe: bool, valor: Any).
    """
    if not path:
        return True, data

    # Parsear path en segmentos: clave o indice
    parts: list[tuple[str, Any]] = []
    for segment in path.split("."):
        if not segment:
            continue
        current = segment
        while current:
            m = re.match(r"^([^\[]+)\[(\d+)\](.*)", current)
            if m:
                parts.append(("key", m.group(1)))
                parts.append(("idx", int(m.group(2))))
                current = m.group(3).lstrip(".")
            else:
                parts.append(("key", current))
                break

    node = data
    for kind, val in parts:
        if node is None:
            return False, None
        if kind == "key":
            if not isinstance(node, dict) or val not in node:
                return False, None
            node = node[val]
        else:
            if not isinstance(node, (list, tuple)) or len(node) <= val:
                return False, None
            node = node[val]

    return True, node


def _check_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True  # tipo desconocido — no falla


# ── SpecValidator ─────────────────────────────────────────────────────────────

class SpecValidator:
    def __init__(self, spec: dict[str, Any]) -> None:
        self._spec = spec

    # ── busqueda por fuente ───────────────────────────────────────────────────

    def _instances_for(
        self,
        event_name: str,
        source: str,
        dl_events: list[dict[str, Any]],
        ga4_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reune todas las instancias del evento segun su fuente."""
        instances: list[dict[str, Any]] = []

        if source in ("dataLayer", "both"):
            for cap in dl_events:
                payload = cap.get("payload", {})
                if payload.get("event") == event_name:
                    instances.append({"source": "dataLayer", "data": payload})

        if source in ("ga4_hit", "both"):
            for hit in ga4_hits:
                if hit.get("event_name") == event_name:
                    # Para hits GA4, los params estan en event_params + raw
                    merged = {**hit.get("event_params", {}), **hit.get("raw", {})}
                    instances.append({"source": "ga4_hit", "data": merged})

        return instances

    # ── validacion de params de una instancia ─────────────────────────────────

    def _check_params(
        self,
        instance_data: dict[str, Any],
        required_params: list[dict[str, Any]],
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Retorna (found_ok, missing, type_wrong) con los keys de cada categoria.
        """
        found_ok: list[str] = []
        missing:  list[str] = []
        type_wrong: list[str] = []

        for param in required_params:
            key      = param["key"]
            expected = param.get("type", "string")
            exists, value = _resolve(instance_data, key)
            if not exists:
                missing.append(key)
            elif not _check_type(value, expected):
                type_wrong.append(key)
            else:
                found_ok.append(key)

        return found_ok, missing, type_wrong

    # ── validacion principal ──────────────────────────────────────────────────

    def validate(
        self,
        dl_events: list[dict[str, Any]],
        ga4_hits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Retorna:
          results: lista detallada por evento
          scores:  {ecommerce, leads, custom, p1} → {ok, total, pct}
          gaps:    eventos no COMPLETO, ordenados por prioridad
        """
        results: list[dict[str, Any]] = []

        for spec_ev in self._spec.get("events", []):
            name     = spec_ev["name"]
            category = spec_ev.get("category", "custom")
            priority = spec_ev.get("priority", "P3")
            source   = spec_ev.get("source", "dataLayer")
            req      = spec_ev.get("required_params", [])
            desc     = spec_ev.get("description", "")
            trigger  = spec_ev.get("trigger", "")

            instances = self._instances_for(name, source, dl_events, ga4_hits)

            if not instances:
                results.append({
                    "event_name":     name,
                    "category":       category,
                    "priority":       priority,
                    "source":         source,
                    "description":    desc,
                    "trigger":        trigger,
                    "status":         "AUSENTE",
                    "found_params":   [],
                    "missing_params": [p["key"] for p in req],
                    "type_errors":    [],
                    "instances_count": 0,
                })
                continue

            # Evaluar la mejor instancia (la que cumple mas params)
            best = ([], list(p["key"] for p in req), [])
            for inst in instances:
                ok, miss, tw = self._check_params(inst["data"], req)
                if len(ok) > len(best[0]):
                    best = (ok, miss, tw)

            found_ok, missing, type_wrong = best

            if not missing and not type_wrong:
                status = "COMPLETO"
            else:
                status = "PARCIAL"

            results.append({
                "event_name":     name,
                "category":       category,
                "priority":       priority,
                "source":         source,
                "description":    desc,
                "trigger":        trigger,
                "status":         status,
                "found_params":   found_ok,
                "missing_params": missing,
                "type_errors":    type_wrong,
                "instances_count": len(instances),
            })

        # ── scores ───────────────────────────────────────────────────────────
        def _score(evs: list[dict]) -> dict[str, Any]:
            ok = sum(1 for e in evs if e["status"] == "COMPLETO")
            total = len(evs)
            return {"ok": ok, "total": total, "pct": round(ok / total * 100, 1) if total else 0.0}

        scores = {
            "ecommerce": _score([r for r in results if r["category"] == "ecommerce"]),
            "leads":     _score([r for r in results if r["category"] == "leads"]),
            "custom":    _score([r for r in results if r["category"] == "custom"]),
            "p1":        _score([r for r in results if r["priority"] == "P1"]),
            "global":    _score(results),
        }

        prio_order = {"P1": 0, "P2": 1, "P3": 2}
        gaps = sorted(
            [r for r in results if r["status"] != "COMPLETO"],
            key=lambda r: (prio_order.get(r["priority"], 9), r["event_name"]),
        )

        return {"results": results, "scores": scores, "gaps": gaps}
