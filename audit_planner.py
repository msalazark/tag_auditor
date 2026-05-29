from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditPlanner:
    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _pick_first(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        return candidates[0] if candidates else None

    def _pick_best(self, candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
        return sorted(candidates, key=lambda item: (item.get("depth", 0), item.get("url", "")))[:count]

    def _url_for_type(self, urls: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
        return [item for item in urls if item.get("type") == type_name]

    def _step_payload(self, step: int, item: dict[str, Any], url_type: str, actions: list[str], spec_filter: list[str]) -> dict[str, Any]:
        return {
            "step": step,
            "url": item.get("url", "infer") if item else "infer",
            "type": url_type,
            "actions": actions,
            "spec_filter": spec_filter,
        }

    def build_plan(self, url_list: dict[str, Any], spec_file: str | None = None) -> dict[str, Any]:
        urls = url_list.get("urls", [])
        by_type = {t: self._url_for_type(urls, t) for t in [
            "home",
            "institutional",
            "content",
            "ecommerce_listing",
            "ecommerce_product",
            "ecommerce_cart",
            "ecommerce_checkout",
            "ecommerce_confirmation",
            "lead_landing",
            "lead_thankyou",
        ]}

        general_steps: list[dict[str, Any]] = []
        home = self._pick_first(by_type["home"])
        if home:
            general_steps.append(self._step_payload(1, home, "home", ["scroll_full", "capture_links"], ["page_view", "scroll_depth"]))

        institutionals = self._pick_best(by_type["institutional"] + by_type["content"], 2)
        for index, item in enumerate(institutionals, start=len(general_steps) + 1):
            general_steps.append(self._step_payload(index, item, item.get("type", "content"), ["scroll_full"], ["page_view"]))

        categories = self._pick_best(by_type["ecommerce_listing"], 2)
        for index, item in enumerate(categories, start=len(general_steps) + 1):
            general_steps.append(self._step_payload(index, item, "ecommerce_listing", ["scroll_full"], ["view_item_list"]))

        contact = self._pick_first(by_type["lead_landing"])
        if contact:
            general_steps.append(self._step_payload(len(general_steps) + 1, contact, "lead_landing", ["scroll_full"], ["page_view"]))

        others = [item for item in urls if item.get("type") == "other"]
        other_steps = self._pick_best(others, 2)
        for index, item in enumerate(other_steps, start=len(general_steps) + 1):
            general_steps.append(self._step_payload(index, item, "other", ["scroll_full"], ["page_view"]))

        ecommerce_steps: list[dict[str, Any]] = []
        ecommerce_steps.append(self._step_payload(1, self._pick_first(by_type["home"]), "home", ["scroll_full"], ["page_view"]))
        ecommerce_steps.append(self._step_payload(2, self._pick_first(by_type["ecommerce_listing"]), "ecommerce_listing", ["scroll_full", "click_first_product"], ["view_item_list"]))
        ecommerce_steps.append(self._step_payload(3, self._pick_first(by_type["ecommerce_product"]), "ecommerce_product", ["scroll_full", "click_add_to_cart"], ["view_item", "add_to_cart"]))
        ecommerce_steps.append(self._step_payload(4, self._pick_first(by_type["ecommerce_cart"]), "ecommerce_cart", ["scroll_full", "click_checkout"], ["add_to_cart", "begin_checkout"]))
        ecommerce_steps.append(self._step_payload(5, self._pick_first(by_type["ecommerce_checkout"]), "ecommerce_checkout", ["scroll_full"], ["begin_checkout"]))
        ecommerce_steps.append(self._step_payload(6, self._pick_first(by_type["ecommerce_confirmation"]), "ecommerce_confirmation", ["scroll_full"], ["purchase"]))

        lead_steps: list[dict[str, Any]] = []
        if by_type["lead_landing"]:
            lead_steps.append(self._step_payload(1, self._pick_first(by_type["lead_landing"]), "lead_landing", ["scroll_full", "fill_form_inputs", "click_submit"], ["page_view", "generate_lead"]))
            lead_steps.append(self._step_payload(2, self._pick_first(by_type["lead_thankyou"]), "lead_thankyou", ["scroll_full"], ["generate_lead"]))

        plan = {
            "domain": url_list.get("domain", ""),
            "discovered_at": url_list.get("discovered_at", ""),
            "spec_file": spec_file or "",
            "journeys": [
                {
                    "id": "general",
                    "name": "Recorrido general del sitio",
                    "steps": general_steps,
                }
            ],
        }

        if any(step["url"] != "infer" for step in ecommerce_steps):
            plan["journeys"].append({
                "id": "ecommerce_funnel",
                "name": "Funnel de compra completo",
                "steps": [step if step["url"] else {**step, "url": "infer"} for step in ecommerce_steps],
            })

        if lead_steps:
            plan["journeys"].append({
                "id": "lead_funnel",
                "name": "Funnel de captación de leads",
                "steps": lead_steps,
            })

        return plan

    def save(self, data: dict[str, Any], path: str | Path) -> Path:
        output_path = Path(path)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
