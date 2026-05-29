from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from audit_planner import AuditPlanner
from runners import EcommerceRunner, LeadRunner, StaticRunner
from site_crawler import SiteCrawler
from url_classifier import URLClassifier


class MultiPageAuditor:
    def __init__(self, root_url: str, output_dir: str = "reports", timeout: int = 3,
                 headless: bool = True, session_file: str | None = None):
        self.root_url = root_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.headless = headless
        self.session_file = session_file

        self.crawler = SiteCrawler(root_url, output_dir=output_dir, timeout=timeout,
                                   headless=headless, session_file=session_file)
        self.classifier = URLClassifier(headless=headless, timeout=timeout)
        self.planner = AuditPlanner(output_dir=output_dir)
        self.static_runner = StaticRunner(headless=headless, timeout=timeout, session_file=session_file)
        self.ecommerce_runner = EcommerceRunner(headless=headless, timeout=timeout, session_file=session_file)
        self.lead_runner = LeadRunner(headless=headless, timeout=timeout, session_file=session_file)

    async def discover_and_plan(self, spec_file: str | None = None) -> dict[str, Any]:
        discovery = await self.crawler.discover()
        classification = await self.classifier.classify(discovery)
        plan = self.planner.build_plan(classification, spec_file=spec_file)
        return plan

    async def _execute_journey(self, journey: dict[str, Any]) -> dict[str, Any]:
        journey_id = journey.get("id", "general")
        if journey_id == "ecommerce_funnel":
            return await self.ecommerce_runner.run_journey(journey)
        if journey_id == "lead_funnel":
            return await self.lead_runner.run_journey(journey)
        return await self.static_runner.run_journey(journey)

    async def run_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        journeys = plan.get("journeys", [])
        tasks = [self._execute_journey(journey) for journey in journeys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        journey_results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for journey, result in zip(journeys, results):
            if isinstance(result, Exception):
                errors.append({"journey_id": journey.get("id"), "error": str(result)})
                journey_results.append({"journey_id": journey.get("id"), "name": journey.get("name"), "status": "failed"})
            else:
                journey_results.append({**result, "status": "completed"})

        output = {
            "domain": plan.get("domain"),
            "discovered_at": plan.get("discovered_at"),
            "spec_file": plan.get("spec_file"),
            "journeys": journey_results,
            "errors": errors,
        }
        return output

    def save(self, data: dict[str, Any], filename: str) -> Path:
        output_path = self.output_dir / filename
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
