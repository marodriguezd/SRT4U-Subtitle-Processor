# application/services/config_service.py
import os
import json
from typing import Any, Dict

class ConfigService:
    """
    Gestiona la configuración y credenciales del usuario de manera persistente en disco.
    """
    DEFAULT_CONFIG = {
        "deepl_api_key": "",
        "deepl_type": "free",  # "free" o "pro"
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "source_lang": "auto",
        "target_lang": "es",
        "preferred_engine": "google",
        "auto_clean": True,
        "preserve_format": True,
        "output_dir": "",
        "ui_language": "auto",
    }

    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "settings.json")
        self.config: Dict[str, Any] = dict(self.DEFAULT_CONFIG)
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
        return path

    def load(self) -> None:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.config.update(data)
            except Exception:
                pass

    def save(self) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error al guardar configuración: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, self.DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.save()
