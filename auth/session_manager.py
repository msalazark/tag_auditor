"""
Orquestador de estrategias de autenticación para auditoría de tags.
Soporta: form_login, token_header, session_inject.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Browser, BrowserContext, Page

from .interactive_auth import InteractiveAuth


class AuthenticationError(Exception):
    pass


class SessionManager:
    """Gestiona sesiones autenticadas para el auditor."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._session_file = Path(config.get("session_file", "auth/sessions/session.json"))
        self._session_file.parent.mkdir(parents=True, exist_ok=True)

    async def get_context(self, browser: Browser) -> BrowserContext:
        """
        Retorna un BrowserContext autenticado.
        Reutiliza sesión guardada si aún es válida; de lo contrario hace login.
        """
        strategy = self.config.get("strategy", "none")

        if strategy == "none":
            return await browser.new_context()
        if strategy == "session_inject":
            return await self._load_session_context(browser)
        if strategy == "token_header":
            return await self._token_header_context(browser)
        if strategy == "form_login":
            if self._is_session_valid():
                print("  Reutilizando sesion guardada...")
                return await self._load_session_context(browser)
            return await self._do_form_login(browser)

        raise AuthenticationError(f"Estrategia desconocida: {strategy}")

    # ─── Estrategias ──────────────────────────────────────────────────────

    async def _do_form_login(self, browser: Browser) -> BrowserContext:
        may_interact = self.config.get("may_require_interaction", False)

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            no_viewport=False,
        )
        page = await context.new_page()

        login_url: str = self.config.get("login_url") or self.config.get("domain", "")
        if not login_url.startswith("http"):
            login_url = f"https://{login_url}"

        await page.goto(login_url)

        creds = self._load_credentials()
        await self._fill_credentials(page, creds)
        await self._submit_login(page)

        interactive = InteractiveAuth(
            notification_mode=self.config.get("notification_mode", "terminal"),
            timeout_seconds=self.config.get("interaction_timeout", 180),
            webhook_url=self.config.get("webhook_url"),
            screenshot_on_pause=True,
            target_domain=self.config.get("domain"),
        )

        # Verificar bloqueos y éxito de login en bucle (hasta 15s)
        for _ in range(15):
            await page.wait_for_timeout(1000)

            block = await interactive.detect_block(page)
            if block:
                print(f"\n  Bloqueo detectado: {block['type']} ({block.get('detail', '')})")
                completed = await interactive.wait_for_human(page, block)
                if not completed:
                    await context.close()
                    raise AuthenticationError(
                        f"Timeout esperando intervencion humana: {block['type']}"
                    )
                continue  # Volver a revisar tras la interacción

            if await self._verify_login_success(page):
                break
        else:
            await context.close()
            raise AuthenticationError("Login no verificado despues de 15 intentos")

        await context.storage_state(path=str(self._session_file))
        self._write_session_meta()
        return context

    async def _load_session_context(self, browser: Browser) -> BrowserContext:
        if not self._session_file.exists():
            raise AuthenticationError(
                f"Archivo de sesion no encontrado: {self._session_file}"
            )
        return await browser.new_context(storage_state=str(self._session_file))

    async def _token_header_context(self, browser: Browser) -> BrowserContext:
        token_env = self.config.get("token_env", "AUDIT_TOKEN")
        token = os.environ.get(token_env, "")
        if not token:
            raise AuthenticationError(
                f"Token no encontrado en variable de entorno: {token_env}"
            )
        header_name = self.config.get("token_header", "Authorization")
        header_value = self.config.get("token_prefix", "Bearer ") + token
        return await browser.new_context(
            extra_http_headers={header_name: header_value}
        )

    # ─── Helpers privados ─────────────────────────────────────────────────

    def _load_credentials(self) -> dict[str, str]:
        creds_env = self.config.get("credentials_env", {})
        user_var = creds_env.get("username", "AUDIT_USER")
        pass_var = creds_env.get("password", "AUDIT_PASS")
        username = os.environ.get(user_var, "")
        password = os.environ.get(pass_var, "")  # Vacío en flows phone+OTP
        if not username:
            raise AuthenticationError(
                f"Credencial de usuario no encontrada. Exporta {user_var}."
            )
        return {"username": username, "password": password}

    async def _fill_credentials(self, page: Page, creds: dict[str, str]) -> None:
        selectors = self.config.get("selectors", {})
        user_sel = selectors.get(
            "username",
            "input[type='email'], input[name='email'], input[name='username'], "
            "input[id*='user'], input[id*='email'], input[type='tel'], "
            "input[name='phone'], input[name='telefono'], input[name='celular']",
        )
        pass_sel = selectors.get("password", "input[type='password']")

        await page.fill(user_sel, creds["username"])

        # Password es opcional — flows phone+OTP no tienen campo password
        if creds.get("password"):
            try:
                pass_el = await page.wait_for_selector(pass_sel, timeout=3000, state="visible")
                if pass_el:
                    await page.fill(pass_sel, creds["password"])
            except Exception:
                pass  # Sin campo password — continuar con OTP

    async def _submit_login(self, page: Page) -> None:
        selectors = self.config.get("selectors", {})
        submit_sel = selectors.get(
            "submit",
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Login'), button:has-text('Iniciar'), "
            "button:has-text('Sign in'), button:has-text('Ingresar'), "
            "button:has-text('Entrar')",
        )
        await page.click(submit_sel)

    async def _verify_login_success(self, page: Page) -> bool:
        check = self.config.get("success_check", {})
        check_type = check.get("type", "url_change")

        if check_type == "url_change":
            expected = check.get("expected_url_contains", "")
            return bool(expected) and expected in page.url

        if check_type == "element_present":
            selector = check.get("selector", "")
            if not selector:
                return False
            el = await page.query_selector(selector)
            return el is not None

        if check_type == "element_absent":
            selector = check.get("selector", "input[type='password']")
            el = await page.query_selector(selector)
            return el is None

        if check_type == "url_not_contains":
            excluded = check.get("excluded_url_contains", "/login")
            return excluded not in page.url

        return False

    def _is_session_valid(self) -> bool:
        meta_file = self._session_file.with_suffix(".meta.json")
        if not self._session_file.exists() or not meta_file.exists():
            return False
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            return time.time() < meta.get("expires_at", 0)
        except Exception:
            return False

    def _write_session_meta(self) -> None:
        ttl_hours = self.config.get("session_ttl_hours", 8)
        meta = {
            "created_at": time.time(),
            "expires_at": time.time() + ttl_hours * 3600,
            "domain": self.config.get("domain", ""),
            "strategy": self.config.get("strategy", "form_login"),
        }
        meta_file = self._session_file.with_suffix(".meta.json")
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
