# Providers de traducción y métricas

La coordinación de traducción es headless y no depende de PyQt6. `TranslationService` resuelve un identificador con `ProviderRegistry`, ejecuta el provider y ofrece:

- `translate_text(...) -> str`: API existente que se conserva para GUI, procesamiento y clientes actuales.
- `translate_with_metrics(...) -> TranslationResult`: resultado estructurado para código nuevo.
- `last_result` / `last_error`: estado del último llamado del hilo actual, compatible con el procesamiento paralelo.

## Arquitectura existente

```text
SubtitleService / GUI / CLI
          ↓
   TranslationService
          ↓
   ProviderRegistry
     ├── GoogleProvider
     ├── DeepLProvider
     └── OpenAICompatibleProvider (openai, llm, ollama)
```

Google conserva su integración opcional `deep-translator` y su fallback HTTP con `urllib`. DeepL mantiene endpoints free/pro, códigos de idioma existentes y cabecera de autenticación. OpenAI, Ollama y endpoints compatibles comparten la implementación HTTP; el endpoint base, modelo y clave continúan configurándose mediante las claves existentes `openai_base_url`, `openai_model` y `openai_api_key`. El prompt, `temperature=0.2`, ruta `/chat/completions` y parámetros anteriores se mantienen. El campo de contexto forma parte del contrato para futuros proveedores; ningún prompt cambia por pasar contexto ahora.

`ollama` y `llm` son alias del endpoint compatible, no implementaciones duplicadas. La resolución tiene una única fuente de verdad: `ProviderRegistry` (`register("openai", OpenAICompatibleProvider, aliases=("llm", "ollama"))`). La CLI pasa el identificador tal cual al servicio, que conserva `requested_provider` (`"ollama"`, `"llm"` u `"openai"`) en las métricas aunque la implementación HTTP sea la misma; así el futuro benchmark distingue la intención del usuario. GUI sigue enviando su selección existente. Agregar un nuevo proveedor requiere implementar `TranslationProvider` y registrarlo una vez.

## Crear y registrar un provider

```python
from application.services.translation_providers import (
    ProviderRegistry,
    ProviderResponse,
    TranslationProvider,
)

class ExampleProvider(TranslationProvider):
    name = "example"
    model = "example-v1"

    def translate(self, text, source_language, target_language, *, context=None):
        # Realizar la llamada al backend y lanzar errores TranslationProviderError.
        return call_example_backend(text, source_language, target_language)

    def translate_detailed(self, text, source_language, target_language, *, context=None):
        translated = self.translate(text, source_language, target_language, context=context)
        return ProviderResponse(translated, model=self.model)

ProviderRegistry.register("example", ExampleProvider, aliases=("example-alias",))
```

El registro es pequeño: `register(name, factory, aliases=...)`, `get(name, config_service=...)`. No hay contenedor de dependencias externo. Los providers deben evitar estado mutable por request y nunca registrar headers, credenciales ni cuerpo de traducción.

## Errores, retries y fallback

El núcleo consume errores de SRT4U: `ProviderConfigurationError`, `ProviderAuthenticationError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderNetworkError`, `ProviderResponseError` y `ProviderUnknownError`. La categoría está disponible como `error_type` y la política de retry como `retryable`. No se filtran excepciones del SDK ni respuestas HTTP completas hacia logs.

Política de seguridad de `error_message`: en fallos normales de provider, `TranslationMetrics.error_message` permanece `None`; el detalle crudo del backend (que podría contener secretos o contenido) nunca se conserva. La categoría viaja en `error_type` y, cuando hay fallback, el tipo original en `fallback_error_type`. Solo errores internos de validación construidos por el propio coordinador (p. ej. texto no cadena, provider desconocido, fallback circular) pueden llevar un mensaje seguro generado localmente.

Los retries son opt-in con `TranslationService(max_retries=N)` y se limitan a errores transitorios/reintentables; el default es cero. Por compatibilidad, el fallback histórico DeepL/OpenAI-compatible → Google se conserva y ahora es explícito en `DEFAULT_FALLBACKS`. Se puede desactivar o cambiar pasando, por ejemplo, `fallbacks={}` o `fallbacks={"openai": ["deepl"]}`. Cada fallback se registra como evento; las métricas contienen provider solicitado, providers usados y `fallback_used`. El fallback puede cambiar el proveedor efectivo y conviene activar `fallbacks={}` cuando se requiera fijar estrictamente una implementación.

## Métricas

`TranslationResult` contiene el texto y un `TranslationMetrics` serializable con `to_dict()`:

- provider y modelo; idiomas; cues, caracteres y palabras de entrada/salida;
- duración en milisegundos, éxito, tipo/mensaje de error, retries y fallback;
- tokens de entrada/salida/total cuando el endpoint los devuelve;
- `estimated_cost`, que permanece `null` hasta que exista un cálculo basado en tarifas fiables.

Los tokens y coste no se inventan: Google y DeepL no dan tokens aquí, así que quedan `null`. El endpoint OpenAI-compatible conserva valores de `usage` recibidos realmente. `SubtitleService.translate_subtitles()` agrega las métricas por cue en `last_translation_metrics`; `ProcessingResult.translation_metrics` las transporta para flujos completos, sin alterar `ProcessingStats`. `duration_ms` agregado es wall-time del lote (tiempo total transcurrido medido con `perf_counter` alrededor de la traducción), no la suma de latencias por cue; en paralelo la suma sobrestimaría el tiempo real percibido por el usuario. Las latencias por cue existen en cada `TranslationMetrics` individual previo a la agregación. No es una métrica de benchmark ni de facturación.

## Configuración y seguridad

Para no romper instalaciones, las claves/API keys mantienen sus nombres en `settings.json` (`deepl_api_key`, `openai_api_key`). El archivo vive en el directorio de configuración de usuario. En POSIX, las escrituras configuran permisos de directorio `0700` y archivo `0600`; en Windows se conserva la ACL heredada del directorio de usuario. Esto no es un almacén criptográfico ni mueve/borra valores de configuraciones antiguas. El uso de un almacén seguro de secretos requeriría una migración compatible con GUI y queda para una decisión separada.

Los logs describen provider, modelo, duración, reintentos, fallback y categorías de error; no incluyen claves ni texto traducido. Errores de HTTP se normalizan sin registrar URL/headers/cuerpo que podrían contener secretos. Evitar pegar credenciales reales en pruebas, issues o repositorios.

## Pruebas

Providers y servicio se prueban con `pytest` y mocks de `urllib.request.urlopen` / registry; el conjunto normal no hace requests de red. Los tests `@pytest.mark.network` de Google son pruebas explícitas de integración y pueden omitirse en runs offline:

```bash
python -m pytest -q tests/test_translation_providers.py tests/test_translation_free.py -m "not network"
python -m ruff check application/services tests/test_translation_providers.py
python -m ruff format --check application/services tests/test_translation_providers.py
```

La GUI continúa usando `engine` y la API string existente, mientras futuras APIs/benchmarks pueden serializar `TranslationResult.to_dict()` sin depender de Qt.
