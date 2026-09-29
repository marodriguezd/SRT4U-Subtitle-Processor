import json
import os
from typing import Any, Dict, Optional

from ..logging_setup import get_logger

logger = get_logger("config")


class ConfigService:
    """Gestiona la configuración y credenciales del usuario de manera persistente."""

    DEFAULT_CONFIG = {
        "deepl_api_key": "",
        "deepl_type": "free",
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "source_lang": "auto",
        "target_lang": "es",
        "preferred_engine": "google",
        "auto_clean": True,
        "preserve_format": True,
        "ui_language": "auto",
    }

    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "settings.json")
        self.config: Dict[str, Any] = dict(self.DEFAULT_CONFIG)
        self.load_error: Optional[str] = None
        self.save_error: Optional[str] = None
        self.load()

    def _get_config_dir(self) -> str:
        if os.name == "nt":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        elif os.uname().sysname == "Darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

        path = os.path.join(base, "SRT4U")
        os.makedirs(path, exist_ok=True)
        if os.name != "nt":
            os.chmod(path, 0o700)
        return path

    def load(self) -> None:
        """Carga la configuración; conserva el comportamiento de valores por defecto."""
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as config_file:
                data = json.load(config_file)
            if not isinstance(data, dict):
                raise ValueError("el contenido no es un objeto JSON")
            self.config.update(data)
            if os.name != "nt":
                os.chmod(self.config_file, 0o600)
            self.load_error = None
        except Exception as exc:
            self.load_error = type(exc).__name__
            logger.warning(
                "No se pudo leer la configuración (%s); se usan los valores por defecto",
                type(exc).__name__,
            )

    def save(self) -> bool:
        """Escribe configuración y claves con permisos restrictivos en POSIX."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            if os.name != "nt":
                os.chmod(self.config_dir, 0o700)
            with open(self.config_file, "w", encoding="utf-8") as config_file:
                json.dump(self.config, config_file, indent=2, ensure_ascii=False)
            if os.name != "nt":
                os.chmod(self.config_file, 0o600)
            self.save_error = None
            return True
        except Exception as exc:
            self.save_error = type(exc).__name__
            logger.error("No se pudo guardar la configuración (%s)", type(exc).__name__)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, self.DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> bool:
        """Asigna un valor y persiste. Devuelve False si la escritura falló."""
        self.config[key] = value
        return self.save()
