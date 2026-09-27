"""
Servicio unificado de traducción con soporte para Google Translate, DeepL y LLMs (OpenAI / Ollama).
Incluye fallback autónomo con urllib estándar sin depender obligatoriamente de librerías externas.
"""

import json
import threading
import urllib.request
import urllib.parse
from typing import Callable, Optional, Dict, List

from ..logging_setup import get_logger
from .config_service import ConfigService

logger = get_logger("translation")

try:
    from deep_translator import GoogleTranslator

    HAS_DEEP_TRANSLATOR = True
except ImportError:
    HAS_DEEP_TRANSLATOR = False


class TranslationService:
    """
    Gestiona la traducción de texto utilizando múltiples motores configurables.
    """

    SUPPORTED_LANGUAGES: List[Dict[str, str]] = [
        {"code": "es", "name": "Español"},
        {"code": "en", "name": "English"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "it", "name": "Italiano"},
        {"code": "pt", "name": "Português"},
        {"code": "ja", "name": "日本語 (Japanese)"},
        {"code": "ko", "name": "한국어 (Korean)"},
        {"code": "zh-CN", "name": "简体中文 (Chinese)"},
        {"code": "ru", "name": "Русский (Russian)"},
    ]

    def __init__(self, config_service: Optional[ConfigService] = None):
        self.config_service = config_service or ConfigService()
        # El último error se guarda por hilo: la traducción en paralelo comparte el
        # servicio entre workers y cada uno debe leer sólo el resultado de su llamada.
        self._tls = threading.local()

    @property
    def last_error(self) -> Optional[str]:
        """
        Descripción del fallo del motor en la última llamada de este hilo
        (`None` si la traducción se completó correctamente).
        """
        return getattr(self._tls, "last_error", None)

    def _set_last_error(self, message: Optional[str]) -> None:
        self._tls.last_error = message

    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        engine: str = "google",
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """
        Traduce un fragmento de texto usando el motor especificado.
        Si el motor falla, devuelve el texto original y el motivo queda en `last_error`.
        """
        engine_lower = engine.lower()

        if engine_lower == "deepl":
            result = self._translate_deepl(text, target_language, source_language)
        elif engine_lower in ["openai", "llm"]:
            result = self._translate_openai(text, target_language, source_language)
        else:
            result = self._translate_google(text, target_language, source_language)

        if progress_callback:
            progress_callback("translation", result)

        return result

    def _translate_google(self, text: str, target: str, source: str) -> str:
        src = "auto" if source == "auto" else source
        if HAS_DEEP_TRANSLATOR:
            try:
                translator = GoogleTranslator(source=src, target=target)
                translated = translator.translate(text)
                self._set_last_error(None)
                return translated
            except Exception as exc:
                logger.debug(
                    "deep-translator falló (se intenta el fallback con urllib): %s", exc
                )

        # Fallback directo con urllib nativo
        try:
            encoded_text = urllib.parse.quote(text)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={target}&dt=t&q={encoded_text}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data[0], list):
                    self._set_last_error(None)
                    return "".join(
                        segment[0] for segment in data[0] if segment and segment[0]
                    )
            self._set_last_error("respuesta inesperada del servicio de traducción")
        except Exception as exc:
            self._set_last_error(str(exc))
            logger.warning(
                "Google Translate no está disponible (%s); se devuelve el texto original",
                exc,
            )

        return text

    def _translate_deepl(self, text: str, target: str, source: str) -> str:
        api_key = self.config_service.get("deepl_api_key", "").strip()
        if not api_key:
            logger.debug("DeepL sin clave API configurada: se usa Google Translate")
            return self._translate_google(text, target, source)

        is_pro = self.config_service.get("deepl_type", "free") == "pro"
        url = (
            "https://api.deepl.com/v2/translate"
            if is_pro
            else "https://api-free.deepl.com/v2/translate"
        )

        target_code = target.upper()
        if target_code == "EN":
            target_code = "EN-US"
        elif target_code == "PT":
            target_code = "PT-PT"

        headers = {
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": [text],
            "target_lang": target_code,
        }
        if source and source != "auto":
            payload["source_lang"] = source.upper()

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                translations = resp_json.get("translations", [])
                if translations:
                    self._set_last_error(None)
                    return translations[0].get("text", text)
            self._set_last_error("respuesta sin traducciones de DeepL")
        except Exception as exc:
            self._set_last_error(f"DeepL: {exc}")
            logger.warning("DeepL falló (%s); se usa Google Translate", exc)
            return self._translate_google(text, target, source)

        return text

    def _translate_openai(self, text: str, target: str, source: str) -> str:
        api_key = self.config_service.get("openai_api_key", "").strip()
        base_url = self.config_service.get(
            "openai_base_url", "https://api.openai.com/v1"
        ).rstrip("/")
        model = self.config_service.get("openai_model", "gpt-4o-mini")

        if not api_key and "localhost" not in base_url and "127.0.0.1" not in base_url:
            logger.debug("OpenAI sin clave API configurada: se usa Google Translate")
            return self._translate_google(text, target, source)

        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        system_prompt = (
            "You are a professional subtitle translator. "
            f"Translate the following subtitle text to language code '{target}'. "
            "Preserve formatting tags (like <i>, <b>, {\\an8}), punctuation, and line breaks. "
            "Output ONLY the translated text, without commentary."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                choices = resp_json.get("choices", [])
                if choices:
                    self._set_last_error(None)
                    return choices[0]["message"]["content"].strip()
            self._set_last_error("respuesta sin resultados del modelo")
        except Exception as exc:
            self._set_last_error(f"OpenAI: {exc}")
            logger.warning("El endpoint LLM falló (%s); se usa Google Translate", exc)
            return self._translate_google(text, target, source)

        return text
