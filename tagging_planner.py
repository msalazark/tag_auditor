"""
Tag Opportunity Planner
Crawlea un sitio web, extrae elementos interactivos y usa Claude API para
identificar oportunidades de tagging GA4/GTM con esfuerzo y valor de negocio.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urldefrag, urlparse

import anthropic
from pydantic import BaseModel
from playwright.async_api import Page


# ── Modelos ──────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "claude-opus-4-7"

MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":   {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":  {"input": 1.00,  "output": 5.00},
}

MODEL_LABELS: dict[str, str] = {
    "claude-haiku-4-5":  "Haiku 4.5   — rápido, costo muy bajo",
    "claude-sonnet-4-6": "Sonnet 4.6  — balance calidad/costo (recomendado)",
    "claude-opus-4-7":   "Opus 4.7    — máxima calidad",
}

AVG_OUTPUT_TOKENS_PER_PAGE = 450


# ── Pydantic models para structured output ───────────────────────────────────

class TaggingOpportunity(BaseModel):
    element: str
    element_type: Literal["button", "link", "form", "cta", "page_event", "video", "other"]
    event_name: str
    parameters: dict[str, str]
    trigger: str
    effort_hours: float
    value: Literal["high", "medium", "low"]
    value_reason: str
    priority: Literal["P1", "P2", "P3"]
    gtm_tag_type: str = "GA4 Event"


class PageAnalysis(BaseModel):
    page_type: Literal[
        "home", "product", "category", "contact",
        "blog", "about", "checkout", "landing", "other"
    ]
    business_context: str
    opportunities: list[TaggingOpportunity]


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """Eres un experto en analytics digital (GA4/GTM) para sitios web latinoamericanos.
Identifica oportunidades de tagging GA4 con valor real para el negocio del cliente.

REGLAS ESTRICTAS:
- Usa snake_case, máximo 40 caracteres por event_name
- NO incluyas eventos automáticos de GTM (gtm.js, gtm.dom, gtm.load, gtm.scrollDepth genérico)
- Prioriza conversiones, micro-conversiones y engagement de alto intención
- Esfuerzo: 0.5h=tag click simple, 1h=parámetros dinámicos, 2h=lógica condicional/form, 4h=e-commerce/complejo
- Valor alto=impacta inversión de marketing directamente
- Valor medio=mejora segmentación o atribución
- Valor bajo=contexto adicional, nice-to-have
- P1=crítico para medición básica del sitio
- P2=importante para optimización de campañas
- P3=nice-to-have, análisis avanzado"""


def _build_prompt(page: dict) -> str:
    domain = urlparse(page["url"]).netloc
    headings = [h.get("text", "") for h in page.get("headings", [])[:6]]
    buttons = page.get("buttons", [])[:20]
    ctas = page.get("ctas", [])[:10]
    links = [
        {"text": l.get("text", ""), "href": l.get("href", "")}
        for l in page.get("links", [])[:20]
        if l.get("text", "").strip()
    ]
    forms = [
        {"fields": f.get("fields", [])[:5], "submit": f.get("submit", "")}
        for f in page.get("forms", [])[:3]
    ]

    return f"""Analiza esta página de {domain} e identifica oportunidades de tagging GA4.

URL: {page["url"]}
Título: {page.get("title", "")}
Headings: {json.dumps(headings, ensure_ascii=False)}
Botones visibles: {json.dumps(buttons, ensure_ascii=False)}
CTAs prominentes: {json.dumps(ctas, ensure_ascii=False)}
Formularios: {json.dumps(forms, ensure_ascii=False)}
Links principales: {json.dumps(links, ensure_ascii=False)}

Identifica TODAS las oportunidades de tagging con valor real. Ignora eventos genéricos de GTM."""


# ── Extracción de elementos ──────────────────────────────────────────────────

async def extract_page_elements(page: Page, url: str) -> dict[str, Any]:
    """Extrae botones, links, formularios y CTAs de una página."""
    try:
        title = await page.title()
    except Exception:
        title = ""

    try:
        headings = await page.eval_on_selector_all(
            "h1, h2, h3",
            "els => els.map(e => ({tag: e.tagName.toLowerCase(), text: e.innerText.trim().slice(0,80)}))"
        )
    except Exception:
        headings = []

    try:
        buttons = await page.eval_on_selector_all(
            "button, input[type=submit], input[type=button], [role=button]",
            "els => els.filter(e => e.offsetParent !== null)"
            ".map(e => (e.innerText||e.value||e.getAttribute('aria-label')||'').trim())"
            ".filter(t => t.length > 1)"
            ".slice(0, 30)"
        )
    except Exception:
        buttons = []

    try:
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.filter(e => e.offsetParent !== null)"
            ".map(e => ({text: e.innerText.trim().slice(0,60), href: e.getAttribute('href')||''}))"
            ".filter(l => l.text.length > 2)"
            ".slice(0, 40)"
        )
    except Exception:
        links = []

    try:
        forms = await page.eval_on_selector_all(
            "form",
            """forms => forms.map(f => ({
                fields: Array.from(f.querySelectorAll(
                    'input[type!=hidden], select, textarea'
                )).map(i => i.getAttribute('name')||i.getAttribute('placeholder')||i.getAttribute('type')||'')
                 .filter(Boolean).slice(0,6),
                submit: (f.querySelector('[type=submit]')||{innerText:''}).innerText||''
            }))"""
        )
    except Exception:
        forms = []

    try:
        ctas = await page.eval_on_selector_all(
            "[class*=cta], [class*=btn-], [class*=button], [class*=call-to-action]",
            "els => [...new Set(els.filter(e => e.offsetParent !== null)"
            ".map(e => e.innerText.trim()).filter(t => t.length > 2))].slice(0,15)"
        )
    except Exception:
        ctas = []

    return {
        "url": url,
        "title": title,
        "headings": headings[:8],
        "buttons": list(dict.fromkeys(b for b in buttons if b))[:25],
        "links": links[:30],
        "forms": forms[:5],
        "ctas": list(dict.fromkeys(c for c in ctas if c))[:12],
    }


# ── Visita de lista de URLs ───────────────────────────────────────────────────

async def visit_url_list(
    urls: list[str],
    headless: bool = True,
    session_file: str | None = None,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """Visita una lista explícita de URLs y extrae sus elementos."""
    ctx_kwargs: dict = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if session_file and Path(session_file).exists():
        ctx_kwargs["storage_state"] = session_file

    from playwright.async_api import async_playwright

    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        for i, url in enumerate(urls, 1):
            if on_progress:
                on_progress(i, len(urls), url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_load_state("load", timeout=8000)
                elements = await extract_page_elements(page, page.url)
                results.append(elements)
            except Exception:
                results.append({"url": url, "error": True,
                                 "title": "", "headings": [], "buttons": [],
                                 "links": [], "forms": [], "ctas": []})

        await browser.close()

    return [r for r in results if not r.get("error")]


# ── Crawler ──────────────────────────────────────────────────────────────────

async def crawl_pages(
    root_url: str,
    max_pages: int = 10,
    headless: bool = True,
    session_file: str | None = None,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """Crawlea el sitio y extrae elementos interactivos de cada página."""
    root = root_url.strip().rstrip("/")
    if not root.startswith("http"):
        root = f"https://{root}"

    netloc = urlparse(root).netloc
    visited: dict[str, dict] = {}
    queue: list[str] = [root]

    ctx_kwargs: dict = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if session_file and Path(session_file).exists():
        ctx_kwargs["storage_state"] = session_file

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        while queue and len(visited) < max_pages:
            url, _ = urldefrag(queue.pop(0))
            if url in visited:
                continue

            if on_progress:
                on_progress(len(visited) + 1, max_pages, url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_load_state("load", timeout=8000)
            except Exception:
                continue

            elements = await extract_page_elements(page, page.url)
            visited[url] = elements

            if len(visited) < max_pages:
                try:
                    hrefs = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.getAttribute('href')||'')"
                    )
                    for href in hrefs:
                        full, _ = urldefrag(urljoin(root, href))
                        parsed = urlparse(full)
                        if (
                            parsed.netloc == netloc
                            and parsed.scheme in ("http", "https")
                            and full not in visited
                            and full not in queue
                        ):
                            queue.append(full)
                except Exception:
                    pass

        await browser.close()

    return [v for v in visited.values()]


# ── Estimación de costo ──────────────────────────────────────────────────────

def estimate_cost_from_tokens(
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    return (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000


def count_tokens_for_pages(
    client: anthropic.Anthropic,
    pages: list[dict],
    model: str,
) -> dict[str, Any]:
    """Usa la API de token counting para estimar el costo real."""
    total_input = 0
    per_page_tokens = []

    for page in pages:
        try:
            result = client.messages.count_tokens(
                model=model,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _build_prompt(page)}],
            )
            tokens = result.input_tokens
        except Exception:
            # Fallback: estimación por caracteres
            tokens = len(_build_prompt(page)) // 3
        total_input += tokens
        per_page_tokens.append(tokens)

    avg_input = total_input // len(pages) if pages else 0
    est_output = len(pages) * AVG_OUTPUT_TOKENS_PER_PAGE

    return {
        "total_input_tokens": total_input,
        "estimated_output_tokens": est_output,
        "avg_input_per_page": avg_input,
        "pages": len(pages),
        "costs": {
            model_id: {
                "input_usd":  total_input * p["input"] / 1_000_000,
                "output_usd": est_output  * p["output"] / 1_000_000,
                "total_usd":  (total_input * p["input"] + est_output * p["output"]) / 1_000_000,
            }
            for model_id, p in MODEL_PRICING.items()
        },
    }


# ── Análisis LLM ─────────────────────────────────────────────────────────────

def analyze_page(
    client: anthropic.Anthropic,
    page_data: dict,
    model: str,
) -> PageAnalysis | None:
    """Analiza una página con Claude y retorna oportunidades de tagging."""
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(page_data)}],
            output_format=PageAnalysis,
        )
        return response.parsed_output
    except Exception as exc:
        # Fallback: intentar parse manual de JSON en la respuesta
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1500,
                system=_SYSTEM + "\n\nResponde ÚNICAMENTE con JSON válido siguiendo el schema de PageAnalysis.",
                messages=[{"role": "user", "content": _build_prompt(page_data)}],
            )
            text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            # Extraer JSON del texto
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return PageAnalysis(**data)
        except Exception:
            pass
        return None
