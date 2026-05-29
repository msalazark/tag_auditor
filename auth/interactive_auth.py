"""
Módulo de autenticación interactiva — pausa y espera intervención humana
para 2FA, OTP, CAPTCHA, preguntas de seguridad, SSO, hardware keys, etc.
"""
from __future__ import annotations

import asyncio
import base64
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"

# Dominios SSO conocidos
_SSO_DOMAINS = frozenset([
    "accounts.google.com",
    "login.microsoftonline.com",
    "login.live.com",
    "auth0.com",
    "okta.com",
    "ping.com",
    "pingidentity.com",
    "onelogin.com",
    "sso.id",
    "adfs.",
    "federation.",
])


class InteractiveAuth:
    """Detecta bloqueos de autenticación y coordina la intervención humana."""

    def __init__(
        self,
        notification_mode: str = "terminal",
        timeout_seconds: int = 180,
        webhook_url: Optional[str] = None,
        screenshot_on_pause: bool = True,
        target_domain: Optional[str] = None,
    ) -> None:
        self.mode = notification_mode
        self.timeout = timeout_seconds
        self.webhook_url = webhook_url
        self.screenshot_on_pause = screenshot_on_pause
        self.target_domain = target_domain
        self._resume_token: Optional[str] = None
        _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ─── API pública ──────────────────────────────────────────────────────

    async def detect_block(self, page) -> Optional[dict]:
        """
        Inspecciona la página y retorna info del bloqueo si detecta uno.
        Retorna None si no requiere intervención humana.
        """
        for detector in [
            self._detect_captcha,
            self._detect_otp,
            self._detect_security_question,
            self._detect_push_wait,
            self._detect_sso_redirect,
            self._detect_hardware_key,
        ]:
            result = await detector(page)
            if result:
                return result
        return None

    async def wait_for_human(self, page, block_info: dict) -> bool:
        """
        Pausa la ejecución, notifica al auditor y espera su intervención.
        Retorna True si el paso fue completado, False si hubo timeout.
        """
        if self.screenshot_on_pause:
            await self._save_screenshot(page, block_info["type"])

        message = self._build_message(page.url, block_info)

        if self.mode == "terminal":
            return await self._wait_terminal(message)
        elif self.mode == "desktop":
            await self._send_desktop_notification(message)
            return await self._wait_terminal(message)
        elif self.mode == "webhook":
            screenshot_b64 = await self._get_screenshot_b64(page)
            return await self._wait_webhook(message, screenshot_b64, block_info)
        else:
            return await self._wait_terminal(message)

    # ─── Detectores ───────────────────────────────────────────────────────

    async def _detect_captcha(self, page) -> Optional[dict]:
        try:
            captcha_iframe = await page.query_selector(
                "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
                "iframe[src*='cloudflare'], iframe[src*='turnstile']"
            )
            if captcha_iframe:
                return {"type": "captcha", "detail": "iframe detected"}

            captcha_el = await page.query_selector(
                ".captcha, #captcha, .g-recaptcha, #g-recaptcha, "
                ".h-captcha, #h-captcha, .cf-turnstile, #cf-turnstile"
            )
            if captcha_el:
                return {"type": "captcha", "detail": "element detected"}

            content = (await page.content()).lower()
            for text in [
                "no soy un robot", "i'm not a robot", "im not a robot",
                "verifica que eres humano", "complete the captcha",
                "verify you are human",
            ]:
                if text in content:
                    return {"type": "captcha", "detail": f"text: {text}"}
        except Exception:
            pass
        return None

    async def _detect_otp(self, page) -> Optional[dict]:
        try:
            otp_attrs = ["otp", "code", "token", "verification", "codigo", "verificacion", "pin"]
            for attr in otp_attrs:
                for prop in ["name", "id", "placeholder"]:
                    el = await page.query_selector(f"input[{prop}*='{attr}']")
                    if el and await el.is_visible():
                        return {"type": "otp", "detail": f"input[{prop}*={attr}]"}

            # Patrón de inputs de un dígito agrupados (OTP split en 4–8 cajas)
            single_digit = await page.query_selector_all(
                "input[type='text'][maxlength='1'], input[type='number'][maxlength='1']"
            )
            if len(single_digit) >= 4:
                return {"type": "otp", "detail": "split digit inputs"}

            content = (await page.content()).lower()
            for text in [
                "ingresa el código", "enter the code", "enter code",
                "código enviado", "code sent", "check your email",
                "revisa tu correo", "mensaje de texto", "sms code",
                "verification code", "código de verificación",
                "two-factor", "two factor", "2fa", "mfa",
                "autenticación de dos",
            ]:
                if text in content:
                    return {"type": "otp", "detail": f"text: {text}"}
        except Exception:
            pass
        return None

    async def _detect_security_question(self, page) -> Optional[dict]:
        try:
            content = (await page.content()).lower()
            for text in [
                "pregunta secreta", "security question",
                "¿cuál es tu", "what is your",
                "pregunta de seguridad",
            ]:
                if text in content:
                    return {"type": "security_question", "detail": f"text: {text}"}

            labels = await page.query_selector_all("label")
            for label in labels:
                label_text = (await label.inner_text()).lower()
                if any(kw in label_text for kw in ["pregunta", "question", "secret"]):
                    return {"type": "security_question", "detail": "label detected"}
        except Exception:
            pass
        return None

    async def _detect_push_wait(self, page) -> Optional[dict]:
        try:
            content = (await page.content()).lower()
            for text in [
                "aprueba en tu aplicación", "approve in your app",
                "abre tu autenticador", "check your authenticator",
                "notificación push", "push notification",
                "approve the sign-in", "waiting for approval",
                "esperando aprobación",
            ]:
                if text in content:
                    return {"type": "push", "detail": f"text: {text}"}
        except Exception:
            pass
        return None

    async def _detect_sso_redirect(self, page) -> Optional[dict]:
        try:
            from urllib.parse import urlparse
            current_host = urlparse(page.url).netloc.lower()

            for sso_domain in _SSO_DOMAINS:
                if sso_domain in current_host:
                    return {"type": "sso", "detail": f"redirected to {current_host}"}

            if self.target_domain:
                target_host = (
                    self.target_domain.lower()
                    .replace("https://", "").replace("http://", "")
                    .split("/")[0]
                )
                auth_keywords = ["auth", "login", "sso", "oauth", "saml", "signin", "callback"]
                if (
                    current_host
                    and current_host != target_host
                    and "localhost" not in current_host
                    and any(kw in page.url.lower() for kw in auth_keywords)
                ):
                    return {"type": "sso", "detail": f"auth redirect to {current_host}"}
        except Exception:
            pass
        return None

    async def _detect_hardware_key(self, page) -> Optional[dict]:
        try:
            content = (await page.content()).lower()
            for text in [
                "yubikey", "hardware key", "security key",
                "touch id", "windows hello", "llave de seguridad",
                "fido", "webauthn", "usb key",
            ]:
                if text in content:
                    return {"type": "hardware_key", "detail": f"text: {text}"}
        except Exception:
            pass
        return None

    # ─── Mensajes ─────────────────────────────────────────────────────────

    def _build_message(self, current_url: str, block_info: dict) -> str:
        messages: dict[str, str] = {
            "captcha": (
                "CAPTCHA detectado\n"
                "   El sitio requiere que resuelvas un CAPTCHA manualmente.\n"
                f"  URL: {current_url}\n"
                "   Resuélvelo en el browser abierto y presiona ENTER."
            ),
            "otp": (
                "CODIGO DE VERIFICACION requerido\n"
                "   El sitio envió un código por SMS o email.\n"
                f"  URL: {current_url}\n"
                "   Ingresa el código en el browser y presiona ENTER."
            ),
            "push": (
                "APROBACION EN APP requerida\n"
                "   El sitio espera que apruebes el login en tu aplicación móvil.\n"
                f"  URL: {current_url}\n"
                "   Aprueba en tu app y presiona ENTER."
            ),
            "sso": (
                "LOGIN SSO detectado\n"
                f"  Redirigido a: {current_url}\n"
                "   Completa el login en el browser y presiona ENTER\n"
                "   cuando estés de vuelta en el sitio objetivo."
            ),
            "security_question": (
                "PREGUNTA DE SEGURIDAD detectada\n"
                f"  URL: {current_url}\n"
                "   Responde la pregunta en el browser y presiona ENTER."
            ),
            "hardware_key": (
                "LLAVE DE SEGURIDAD requerida\n"
                f"  URL: {current_url}\n"
                "   El sitio requiere YubiKey u otro dispositivo hardware.\n"
                "   Inserta tu dispositivo, actívalo y presiona ENTER."
            ),
        }
        return messages.get(block_info["type"], (
            f"INTERVENCION REQUERIDA ({block_info['type']})\n"
            f"  URL: {current_url}\n"
            "   Completa el paso en el browser y presiona ENTER."
        ))

    # ─── Modos de espera ─────────────────────────────────────────────────

    async def _wait_terminal(self, message: str) -> bool:
        print("\n" + "─" * 60)
        print(message)
        print("─" * 60)

        pressed = threading.Event()

        def _read():
            try:
                sys.stdin.readline()
            except Exception:
                pass
            pressed.set()

        t = threading.Thread(target=_read, daemon=True)
        t.start()

        start = time.time()
        while time.time() - start < self.timeout:
            remaining = int(self.timeout - (time.time() - start))
            sys.stdout.write(f"\r  Esperando... {remaining}s (ENTER para continuar) ")
            sys.stdout.flush()
            if pressed.is_set():
                print("\n  Continuando auditoria...\n")
                return True
            await asyncio.sleep(1)

        print(f"\n  Timeout ({self.timeout}s). Paso marcado como SKIPPED.\n")
        return False

    async def _wait_webhook(
        self, message: str, screenshot_b64: str, block_info: dict
    ) -> bool:
        import uuid

        try:
            import aiohttp
        except ImportError:
            print("  [WARN] aiohttp no disponible — usando modo terminal")
            return await self._wait_terminal(message)

        self._resume_token = str(uuid.uuid4())
        payload = {
            "event": "human_required",
            "block_type": block_info["type"],
            "detail": block_info.get("detail", ""),
            "message": message,
            "screenshot_base64": screenshot_b64,
            "resume_token": self._resume_token,
            "expires_at": (datetime.now() + timedelta(seconds=self.timeout)).isoformat(),
        }

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as exc:
            print(f"  [WARN] Webhook falló: {exc} — usando modo terminal")
            return await self._wait_terminal(message)

        resume_file = Path(tempfile.gettempdir()) / f"audit_resume_{self._resume_token}"
        start = time.time()
        print(f"  Webhook enviado. Token: {self._resume_token}")
        print(f"  Para continuar manualmente: crear archivo {resume_file}")

        while time.time() - start < self.timeout:
            if resume_file.exists():
                resume_file.unlink(missing_ok=True)
                print("  Resume recibido. Continuando...")
                return True
            await asyncio.sleep(5)

        print(f"  Timeout ({self.timeout}s). Paso marcado como SKIPPED.")
        return False

    async def _send_desktop_notification(self, message: str) -> None:
        title = "Tag Auditor — Intervencion requerida"
        short_msg = message.split("\n")[0]
        system = platform.system()

        try:
            if system == "Darwin":
                subprocess.run(
                    ["osascript", "-e",
                     f'display notification "{short_msg}" with title "{title}" sound name "Ping"'],
                    check=False, timeout=5,
                )
            elif system == "Linux":
                subprocess.run(["notify-send", title, short_msg], check=False, timeout=5)
            elif system == "Windows":
                try:
                    from plyer import notification as plyer_notif
                    plyer_notif.notify(
                        title=title, message=short_msg,
                        app_name="Tag Auditor", timeout=10,
                    )
                except ImportError:
                    # Fallback vía PowerShell BurntToast / toast nativo
                    ps = (
                        f'$xml = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,'
                        f'ContentType=WindowsRuntime]::new();'
                        f'$xml.loadXml(\'<toast><visual><binding template="ToastText01">'
                        f'<text id="1">{short_msg}</text></binding></visual></toast>\');'
                        f'$toast=[Windows.UI.Notifications.ToastNotification,'
                        f'Windows.UI.Notifications,ContentType=WindowsRuntime]::new($xml);'
                        f'[Windows.UI.Notifications.ToastNotificationManager,'
                        f'Windows.UI.Notifications,ContentType=WindowsRuntime]'
                        f'::CreateToastNotifier("Tag Auditor").Show($toast);'
                    )
                    subprocess.run(["powershell", "-Command", ps], check=False, timeout=10)
        except Exception:
            pass  # Fallback silencioso — el mensaje de terminal ya está visible

    # ─── Utilidades de screenshot ─────────────────────────────────────────

    async def _save_screenshot(self, page, block_type: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SCREENSHOTS_DIR / f"{block_type}_{timestamp}.png"
        try:
            await page.screenshot(path=str(path), full_page=False)
        except Exception:
            pass
        return path

    async def _get_screenshot_b64(self, page) -> str:
        try:
            data = await page.screenshot(full_page=False)
            return base64.b64encode(data).decode("utf-8")
        except Exception:
            return ""
