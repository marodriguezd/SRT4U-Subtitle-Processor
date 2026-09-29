"""Provider contract, normalized errors, registry, and existing translation backends."""

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService

logger = get_logger("translation")

#: Host names that are unambiguously this machine.
_LOCAL_HOSTNAMES = {"localhost", "::1", "0:0:0:0:0:0:0:1"}


def is_loopback_host(hostname: Optional[str]) -> bool:
    """True when ``hostname`` provably refers to this machine.

    Policy (deep-audit M6): only the loopback interface is trusted. The whole
    ``127.0.0.0/8`` range and the "unspecified" address (``0.0.0.0`` / ``::``,
    which a client connecting to it reaches locally) qualify; private LAN
    addresses such as ``192.168.1.50`` deliberately do **not**, because a
    machine on the LAN is not the local machine and must not silently get the
    keyless/cleartext exemptions.
    """
    if not hostname:
        return False
    host = hostname.strip().strip("[]").lower()
    if host in _LOCAL_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_unspecified)


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never across an origin boundary.

    ``urllib``'s stock handler copies every request header — including
    ``Authorization`` — onto the redirect target, so a 302 from a configured
    (or hijacked) endpoint exfiltrates the API key to whoever chose the
    ``Location`` (deep-audit M4). Same-origin redirects are still allowed
    because self-hosted servers legitimately use them to add a trailing slash
    or move a path.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(req.full_url) != _origin(newurl):
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                "redirección entre orígenes rechazada",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _origin(url: str) -> tuple:
    parsed = urllib.parse.urlparse(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower(),
        parsed.port,
    )


def _open(request, timeout: float):
    """Open ``request`` under the same-origin redirect policy.

    This is the single network seam for every provider, so tests and the
    redirect policy cannot drift apart.

    ``build_opener`` installs the stock handlers *before* any custom ones and
    ``OpenerDirector.add_handler`` keeps the first implementation of
    ``http_error_30x`` it sees, so passing the subclass there is silently
    ignored. The opener is therefore assembled by hand with our redirect
    handler in the stock handler's place.
    """
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler,
        urllib.request.HTTPHandler,
        urllib.request.HTTPDefaultErrorHandler,
        _SameOriginRedirectHandler,
        urllib.request.HTTPSHandler,
        urllib.request.HTTPErrorProcessor,
    ):
        opener.add_handler(handler())
    return opener.open(request, timeout=timeout)


try:
    from deep_translator import GoogleTranslator

    HAS_DEEP_TRANSLATOR = True
except ImportError:
    GoogleTranslator = None
    HAS_DEEP_TRANSLATOR = False


class TranslationProviderError(Exception):
    """Base error exposed to the translation coordinator; never contains credentials."""

    error_type = "unknown"
    retryable = False

    def __init__(self, message: str, *, retry_count: int = 0):
        super().__init__(message)
        self.retry_count = retry_count


class ProviderConfigurationError(TranslationProviderError):
    error_type = "configuration"


class ProviderAuthenticationError(TranslationProviderError):
    error_type = "authentication"


class ProviderRateLimitError(TranslationProviderError):
    error_type = "rate_limit"
    retryable = True


class ProviderTimeoutError(TranslationProviderError):
    error_type = "timeout"
    retryable = True


class ProviderNetworkError(TranslationProviderError):
    error_type = "network"
    retryable = True


class ProviderResponseError(TranslationProviderError):
    error_type = "invalid_response"


class ProviderUnknownError(TranslationProviderError):
    error_type = "unknown"


class TranslationProvider(ABC):
    """Provider contract independent of a specific translation backend."""

    name = "provider"
    model: Optional[str] = None

    @abstractmethod
    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        context: Optional[str] = None,
    ) -> str:
        """Translate one text, raising a normalized provider exception on failure."""

    def translate_detailed(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        context: Optional[str] = None,
    ) -> "ProviderResponse":
        return ProviderResponse(
            text=self.translate(
                text, source_language, target_language, context=context
            ),
            model=self.model,
        )


@dataclass
class ProviderResponse:
    """Translation payload plus optional provider-reported usage metadata."""

    text: str
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None

    def to_dict(self):
        return asdict(self)


class ProviderRegistry:
    """Small extensible registry; aliases resolve to the same provider factory."""

    _factories: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, factory, *, aliases=(), replace: bool = False) -> None:
        if not callable(factory):
            raise TypeError("la factory de provider debe ser invocable")
        names = (name, *aliases)
        normalized = tuple(cls._normalize(value) for value in names)
        if any(not value for value in normalized):
            raise ProviderConfigurationError(
                "los nombres y alias no pueden estar vacíos"
            )
        if any(value in cls._factories for value in normalized) and not replace:
            raise ValueError(f"provider ya registrado: {name}")
        for value in normalized:
            cls._factories[value] = factory

    @classmethod
    def get(cls, name: str, config_service: Optional[ConfigService] = None):
        normalized = cls._normalize(name)
        try:
            factory = cls._factories[normalized]
        except KeyError as exc:
            raise ProviderConfigurationError(f"provider no soportado: {name}") from exc
        provider = factory(config_service=config_service)
        if not isinstance(provider, TranslationProvider):
            raise ProviderConfigurationError(
                f"la factory '{name}' no devolvió un TranslationProvider válido"
            )
        return provider

    @classmethod
    def names(cls):
        return tuple(sorted(cls._factories))

    @classmethod
    def supports(cls, name: str) -> bool:
        """True when ``name`` (or an alias) resolves to a registered provider."""
        try:
            return cls._normalize(name) in cls._factories
        except ProviderConfigurationError:
            return False

    @staticmethod
    def _normalize(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ProviderConfigurationError("el nombre del provider es obligatorio")
        return name.strip().casefold()


class GoogleProvider(TranslationProvider):
    name = "google"

    def __init__(self, config_service: Optional[ConfigService] = None):
        self.config_service = config_service
        self._deep_translator_enabled = HAS_DEEP_TRANSLATOR

    def set_deep_translator_enabled(self, enabled: bool) -> None:
        self._deep_translator_enabled = enabled

    def translate(self, text, source_language, target_language, *, context=None):
        src = "auto" if source_language == "auto" else source_language
        if self._deep_translator_enabled and GoogleTranslator:
            try:
                translated = GoogleTranslator(
                    source=src, target=target_language
                ).translate(text)
                if not isinstance(translated, str) or not translated.strip():
                    raise ProviderResponseError("Google devolvió una traducción vacía")
                return translated
            except ProviderResponseError:
                raise
            except Exception as exc:
                logger.debug(
                    "deep-translator falló (se intenta el fallback con urllib): %s",
                    type(exc).__name__,
                )

        query = urllib.parse.urlencode(
            {"client": "gtx", "sl": src, "tl": target_language, "dt": "t", "q": text}
        )
        request = urllib.request.Request(
            f"https://translate.googleapis.com/translate_a/single?{query}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        try:
            with _open(request, 10) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not data or not isinstance(data[0], list):
                raise ProviderResponseError("Google devolvió una respuesta inesperada")
            translated = "".join(
                segment[0] for segment in data[0] if segment and segment[0]
            )
            if not translated:
                raise ProviderResponseError("Google devolvió una traducción vacía")
            return translated
        except TranslationProviderError:
            raise
        except Exception as exc:
            raise _normalize_error(exc, "Google Translate") from exc

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        return ProviderResponse(
            self.translate(text, source_language, target_language, context=context),
            model=None,
        )


class DeepLProvider(TranslationProvider):
    name = "deepl"
    model = None

    def __init__(self, config_service: Optional[ConfigService] = None):
        self.config_service = config_service or ConfigService()

    def translate(self, text, source_language, target_language, *, context=None):
        return self.translate_detailed(
            text, source_language, target_language, context=context
        ).text

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        api_key = str(self.config_service.get("deepl_api_key", "")).strip()
        if not api_key:
            raise ProviderConfigurationError("DeepL API key no configurada")
        is_pro = self.config_service.get("deepl_type", "free") == "pro"
        url = (
            "https://api.deepl.com/v2/translate"
            if is_pro
            else "https://api-free.deepl.com/v2/translate"
        )
        target_code = target_language.upper()
        if target_code == "EN":
            target_code = "EN-US"
        elif target_code == "PT":
            target_code = "PT-PT"
        payload = {"text": [text], "target_lang": target_code}
        if source_language and source_language != "auto":
            payload["source_lang"] = source_language.upper()
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"DeepL-Auth-Key {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with _open(request, 10) as response:
                data = json.loads(response.read().decode("utf-8"))
            translations = data.get("translations", [])
            translated = translations[0].get("text") if translations else None
            if not isinstance(translated, str) or not translated:
                raise ProviderResponseError(
                    "DeepL devolvió una respuesta sin traducciones"
                )
            return ProviderResponse(translated, model=self.model)
        except TranslationProviderError:
            raise
        except Exception as exc:
            raise _normalize_error(exc, "DeepL") from exc


class OpenAICompatibleProvider(TranslationProvider):
    name = "openai"

    def __init__(self, config_service: Optional[ConfigService] = None):
        self.config_service = config_service or ConfigService()
        self.base_url = str(
            self.config_service.get("openai_base_url", "https://api.openai.com/v1")
        ).rstrip("/")
        self.model = str(self.config_service.get("openai_model", "gpt-4o-mini"))
        parsed_url = urllib.parse.urlparse(self.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ProviderConfigurationError("la URL base del endpoint no es válida")
        self._local_endpoint = is_loopback_host(parsed_url.hostname)
        # Deep-audit M5: cleartext HTTP is only acceptable when the request can
        # never leave the machine. For anything else the API key would travel
        # unencrypted, so the configuration is rejected instead of warned about.
        if parsed_url.scheme == "http" and not self._local_endpoint:
            raise ProviderConfigurationError(
                "los endpoints remotos requieren HTTPS; sólo se permite HTTP "
                "para localhost, 127.0.0.0/8 o ::1"
            )

    def _credentials(self):
        api_key = str(self.config_service.get("openai_api_key", "")).strip()
        if not api_key and not self._local_endpoint:
            raise ProviderConfigurationError("API key para el endpoint no configurada")
        return api_key

    def _payload(self, text, target_language):
        # Mantener el prompt y los parámetros originales para compatibilidad.
        system_prompt = (
            "You are a professional subtitle translator. "
            f"Translate the following subtitle text to language code '{target_language}'. "
            "Preserve formatting tags (like <i>, <b>, {\\an8}), punctuation, and line breaks. "
            "Output ONLY the translated text, without commentary."
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

    def translate(self, text, source_language, target_language, *, context=None):
        return self.translate_detailed(
            text, source_language, target_language, context=context
        ).text

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        api_key = self._credentials()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(self._payload(text, target_language)).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
            },
            method="POST",
        )
        try:
            with _open(request, 15) as response:
                data = json.loads(response.read().decode("utf-8"))
            choices = data.get("choices", [])
            if not choices:
                raise ProviderResponseError(
                    "endpoint compatible devolvió choices vacío"
                )
            translated = choices[0].get("message", {}).get("content")
            if not isinstance(translated, str) or not translated.strip():
                raise ProviderResponseError(
                    "endpoint compatible devolvió contenido inválido"
                )
            usage = data.get("usage") or {}
            return ProviderResponse(
                translated.strip(),
                model=data.get("model") or self.model,
                input_tokens=_optional_int(
                    usage.get("prompt_tokens", usage.get("input_tokens"))
                ),
                output_tokens=_optional_int(
                    usage.get("completion_tokens", usage.get("output_tokens"))
                ),
                total_tokens=_optional_int(usage.get("total_tokens")),
            )
        except TranslationProviderError:
            raise
        except Exception as exc:
            raise _normalize_error(exc, "endpoint compatible") from exc


def _optional_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _normalize_error(exc: Exception, provider: str) -> TranslationProviderError:
    if isinstance(exc, TranslationProviderError):
        return exc
    if isinstance(exc, (TimeoutError,)) or (
        isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)
    ):
        return ProviderTimeoutError(f"{provider}: timeout")
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (301, 302, 303, 307, 308):
            # A cross-origin redirect is refused on purpose; say so instead of
            # reporting a meaningless status code.
            return ProviderResponseError(
                f"{provider}: redirección rechazada ({exc.reason or exc.code})"
            )
        if exc.code in (401, 403):
            return ProviderAuthenticationError(
                f"{provider}: autenticación rechazada (HTTP {exc.code})"
            )
        if exc.code == 429:
            return ProviderRateLimitError(
                f"{provider}: límite de solicitudes (HTTP 429)"
            )
        if exc.code >= 500:
            return ProviderNetworkError(
                f"{provider}: error transitorio HTTP {exc.code}"
            )
        return ProviderResponseError(f"{provider}: respuesta HTTP {exc.code}")
    if isinstance(exc, urllib.error.URLError) or isinstance(
        exc, (ConnectionError, OSError)
    ):
        return ProviderNetworkError(f"{provider}: error de red ({type(exc).__name__})")
    if isinstance(exc, (json.JSONDecodeError, KeyError, IndexError, TypeError)):
        return ProviderResponseError(
            f"{provider}: respuesta no válida ({type(exc).__name__})"
        )
    return ProviderUnknownError(f"{provider}: error inesperado ({type(exc).__name__})")


ProviderRegistry.register("google", GoogleProvider)
ProviderRegistry.register("deepl", DeepLProvider)
ProviderRegistry.register("openai", OpenAICompatibleProvider, aliases=("llm", "ollama"))
