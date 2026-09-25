# application/services/i18n_service.py
"""
Servicio centralizado de internacionalización (i18n) para SRT4U.
Soporta detección automática del idioma del sistema y cambio dinámico entre:
- Español (es)
- English (en)
- Português (pt)
- Deutsch (de)
- Italiano (it)
- 简体中文 (zh-CN)
"""
import os
import locale
from typing import Dict, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QLocale
from .config_service import ConfigService


class I18nService(QObject):
    """
    Gestor reactivo de idioma y catálogo de traducciones de la interfaz.
    """
    language_changed = pyqtSignal(str)

    SUPPORTED_LANGUAGES = {
        "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
        "es": {"name": "Spanish", "native": "Español", "flag": "🇪🇸"},
        "pt": {"name": "Portuguese", "native": "Português", "flag": "🇵🇹"},
        "de": {"name": "German", "native": "Deutsch", "flag": "🇩🇪"},
        "it": {"name": "Italian", "native": "Italiano", "flag": "🇮🇹"},
        "zh-CN": {"name": "Simplified Chinese", "native": "简体中文", "flag": "🇨🇳"},
    }

    _instance: Optional["I18nService"] = None

    TRANSLATIONS: Dict[str, Dict[str, str]] = {
        # ------------------ EN (ENGLISH) ------------------
        "en": {
            # Navigation
            "nav.home": "Home",
            "nav.translate": "Translation Studio",
            "nav.clean": "Clean",
            "nav.convert": "Convert",
            "nav.batch": "Batch Processing",
            "nav.settings": "Settings",
            "nav.about": "About",

            # Top bar
            "topbar.theme_tooltip": "Toggle dark / light theme",
            "topbar.lang_tooltip": "Change interface language",
            "topbar.lang_auto": "🌐 Auto (System)",

            # Home Page
            "home.title": "Translate Subtitles",
            "home.subtitle": "Select your file, target language and processing options.",
            "home.source_lang": "Source Language",
            "home.target_lang": "Target Language",
            "home.engine": "Translation Engine",
            "home.clean_title": "Automatic cleaning",
            "home.clean_desc": "Removes spam, URLs, and ads",
            "home.format_title": "Preserve format",
            "home.format_desc": "Keep styles and tags (<i>, <b>, ASS)",
            "home.translate_title": "Translate text",
            "home.translate_desc": "Translate dialogues to target language",
            "home.btn_process": "▶ Start processing",

            # Dropzone
            "dropzone.title": "Drag your subtitle file here",
            "dropzone.subtitle": "or click to browse",
            "dropzone.formats": "Supported formats: .srt, .ass, .vtt, .txt",
            "dropzone.size": "Size: {size:.1f} KB",
            "dropzone.video_detected": "Video detected: {name}",
            "dropzone.replace_hint": "Click or drag another file to replace",
            "dropzone.dialog_title": "Select subtitle",
            "dropzone.filter": "Subtitles (*.srt *.ass *.vtt *.txt);;All files (*.*)",

            # Preview / Translation Studio
            "preview.title": "Translation Studio",
            "preview.subtitle": "Preview video, edit subtitles line by line and synchronize.",
            "preview.btn_open": "📁 Open Subtitle",
            "preview.btn_save": "💾 Save Subtitle",
            "preview.btn_burn": "🔥 Burn into Video",
            "preview.search_placeholder": "🔍 Search in original or translation...",
            "preview.sub_count_zero": "0 subtitles",
            "preview.sub_count_all": "Total: {total} subtitles",
            "preview.sub_count_filtered": "Showing {visible} of {total}",
            "preview.autoscroll": "Auto-scroll with video",
            "preview.col_idx": "#",
            "preview.col_start": "Start",
            "preview.col_end": "End",
            "preview.col_orig": "Original",
            "preview.col_trans": "Translation",
            "preview.btn_jump": "▶ Jump to video",
            "preview.tag_orig": "ORIGINAL",
            "preview.tag_edit": "TRANSLATION / EDIT ✏️",
            "preview.btn_load_video": "🎬 Load Video",
            "preview.video_filter": "Videos (*.mp4 *.mkv *.webm *.avi *.mov);;All files (*.*)",
            "preview.save_dialog_title": "Save edited subtitle",

            # Clean Page
            "clean.title": "Clean Subtitles",
            "clean.subtitle": "Remove ads, links, and fansub watermarks without modifying timings.",
            "clean.btn_clean": "🧹 Clean File Now",

            # Convert Page
            "convert.title": "Format Conversion",
            "convert.subtitle": "Convert between SRT, VTT, ASS and TXT while preserving synchronization.",
            "convert.target_label": "Target format:",
            "convert.btn_convert": "🔄 Convert and Save",

            # Batch Page
            "batch.title": "Batch Processing",
            "batch.subtitle": "Translate, clean, or convert multiple files in parallel.",
            "batch.btn_add": "➕ Add Subtitles",
            "batch.btn_clear": "🗑️ Clear List",
            "batch.col_file": "File",
            "batch.col_size": "Size",
            "batch.col_format": "Format",
            "batch.col_status": "Status",
            "batch.btn_start": "▶ Process All Files",
            "batch.status_queued": "In queue",
            "batch.status_processing": "Processing...",
            "batch.status_completed": "Completed",
            "batch.status_error": "Error: {err}",

            # Settings Page
            "settings.title": "Settings",
            "settings.lang_card_title": "Interface Language",
            "settings.lang_card_desc": "Select the language of the application interface or detect automatically.",
            "settings.lang_auto": "🌐 Automatic (System)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "API key for high-fidelity translations.",
            "settings.deepl_placeholder": "DeepL API Key (e.g. 12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API",
            "settings.deepl_pro": "DeepL Pro API",
            "settings.openai_title": "OpenAI / Compatible Endpoint (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "API Key (optional for local endpoints)",
            "settings.openai_url_placeholder": "Base URL (e.g. https://api.openai.com/v1 or http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "Model (e.g. gpt-4o-mini)",
            "settings.btn_save": "💾 Save Settings",
            "settings.save_success": "Settings saved successfully!",

            # Completed Page
            "completed.title": "Processing Completed",
            "completed.subtitle": "The file has been processed and saved successfully.",
            "completed.card_lines": "processed lines",
            "completed.card_deleted": "deleted lines",
            "completed.card_time": "total time",
            "completed.btn_open_file": "📄 Open File",
            "completed.btn_open_folder": "📂 Show in Explorer",
            "completed.btn_to_preview": "👁️ View in Studio",
            "completed.summary_title": "Summary of Changes",
            "completed.sum1": "✓ Spam, URLs, and unwanted markers cleaned",
            "completed.sum2": "✓ Original timing and structure preserved",
            "completed.sum3": "✓ Output file saved successfully",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "Stable Cross-Platform Version • Autonomous Static FFmpeg",
            "about.desc": "Desktop app to translate, edit, clean, and burn subtitles into video with real-time synchronization and universal support for .srt, .vtt, .ass, and .txt.",
            "about.author_title": "Developer",
            "about.author_role": "Lead Developer & Architect",
            "about.author_location": "Madrid, Spain",
            "about.btn_profile": "🌐 GitHub Profile",
            "about.btn_repo": "⭐ Repository",
            "about.license_title": "Legal License & Terms of Use",
            "about.license_name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International",
            "about.license_desc": "This software is distributed under the CC BY-NC-SA 4.0 license. You are free to share and adapt the material under the following terms:",
            "about.perm_title": "PERMITTED (FREE USE)",
            "about.perm_1": "✓ Share, copy and redistribute the code and application",
            "about.perm_2": "✓ Adapt, remix, transform and build upon the software",
            "about.perm_3": "✓ Personal, educational and non-commercial research use",
            "about.restr_title": "CONDITIONS & RESTRICTIONS",
            "about.restr_1": "⚠️ Attribution (BY): Credit the author (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 Non-Commercial (NC): Commercial sale or monetized redistribution prohibited",
            "about.restr_3": "🔄 ShareAlike (SA): Derivative works must carry this identical CC license",
            "about.btn_open_license": "📜 Open LICENSE file",
            "about.btn_web_deed": "🌐 View CC BY-NC-SA 4.0 Deed",

            # Burn In Dialog
            "burn.dialog_title": "Burn Subtitles into Video (Hardsub)",
            "burn.video_card_title": "Video and Output Paths",
            "burn.lbl_video_source": "Source video:",
            "burn.lbl_output_file": "Output video:",
            "burn.btn_browse": "Browse...",
            "burn.style_card_title": "Subtitle Style",
            "burn.lbl_font_size": "Font size:",
            "burn.lbl_font_color": "Font color:",
            "burn.lbl_bg_box": "Background box:",
            "burn.lbl_font_family": "Font family:",
            "burn.color_white": "⚪ White",
            "burn.color_yellow": "🟡 Yellow",
            "burn.color_cyan": "🔵 Cyan",
            "burn.box_none": "None (Border only)",
            "burn.box_trans": "Semitransparent box",
            "burn.box_solid": "Solid opaque box",
            "burn.btn_burn": "🔥 Burn subtitles into video",
            "burn.btn_cancel": "Cancel",
            "burn.rendering_title": "Rendering subtitles...",
            "burn.encoding_status": "Encoding video with FFmpeg...",
            "burn.speed": "Speed: {speed}",
            "burn.eta": "Remaining time: {eta}",
            "burn.btn_play": "▶ Play video",
            "burn.btn_folder": "📂 Open folder",
            "burn.btn_close": "Close",

            # Alerts & Messages
            "alert.file_req_title": "File required",
            "alert.file_req_desc": "Drag or select a subtitle file first.",
            "alert.no_subs_title": "No subtitles",
            "alert.no_subs_desc": "No subtitles available to burn into video.\nLoad a subtitle file first or process one.",
            "alert.conv_success_title": "Conversion completed",
            "alert.conv_success_desc": "File converted and saved to:\n{path}",
            "alert.conv_error_title": "Conversion error",
            "alert.save_success_title": "Saved successfully",
            "alert.save_success_desc": "Subtitle saved to:\n{path}",
            "alert.burn_success_title": "Burn completed",
            "alert.burn_success_desc": "Video rendered successfully with hardcoded subtitles:\n{path}",
        },

        # ------------------ ES (ESPAÑOL) ------------------
        "es": {
            # Navigation
            "nav.home": "Inicio",
            "nav.translate": "Traducir",
            "nav.clean": "Limpiar",
            "nav.convert": "Convertir",
            "nav.batch": "Procesamiento por lote",
            "nav.settings": "Configuración",
            "nav.about": "Acerca de",

            # Top bar
            "topbar.theme_tooltip": "Alternar modo oscuro / claro",
            "topbar.lang_tooltip": "Cambiar idioma de la interfaz",
            "topbar.lang_auto": "🌐 Automático (Sistema)",

            # Home Page
            "home.title": "Traducir subtítulos",
            "home.subtitle": "Selecciona tu archivo, el idioma de destino y las opciones de procesamiento.",
            "home.source_lang": "Idioma de origen",
            "home.target_lang": "Idioma de destino",
            "home.engine": "Motor de traducción",
            "home.clean_title": "Limpieza automática",
            "home.clean_desc": "Elimina spam, URLs y publicidad",
            "home.format_title": "Conservar formato",
            "home.format_desc": "Mantiene estilos y etiquetas (<i>, <b>, ASS)",
            "home.translate_title": "Traducir texto",
            "home.translate_desc": "Traduce los diálogos al idioma de destino",
            "home.btn_process": "▶ Iniciar procesamiento",

            # Dropzone
            "dropzone.title": "Arrastra tu archivo de subtítulos aquí",
            "dropzone.subtitle": "o haz clic para seleccionar",
            "dropzone.formats": "Formatos soportados: .srt, .ass, .vtt, .txt",
            "dropzone.size": "Tamaño: {size:.1f} KB",
            "dropzone.video_detected": "Video detectado: {name}",
            "dropzone.replace_hint": "Haz clic o arrastra otro archivo para reemplazar",
            "dropzone.dialog_title": "Seleccionar subtítulo",
            "dropzone.filter": "Subtítulos (*.srt *.ass *.vtt *.txt);;Todos los archivos (*.*)",

            # Preview / Translation Studio
            "preview.title": "Estudio de Traducción",
            "preview.subtitle": "Previsualiza vídeo, edita subtítulos frase a frase y sincroniza.",
            "preview.btn_open": "📁 Abrir subtítulo",
            "preview.btn_save": "💾 Guardar subtítulo",
            "preview.btn_burn": "🔥 Incrustar en vídeo",
            "preview.search_placeholder": "🔍 Buscar por texto en original o traducción...",
            "preview.sub_count_zero": "0 subtítulos",
            "preview.sub_count_all": "Total: {total} subtítulos",
            "preview.sub_count_filtered": "Mostrando {visible} de {total}",
            "preview.autoscroll": "Auto-scroll con vídeo",
            "preview.col_idx": "#",
            "preview.col_start": "Inicio",
            "preview.col_end": "Fin",
            "preview.col_orig": "Original",
            "preview.col_trans": "Traducción",
            "preview.btn_jump": "▶ Saltar a vídeo",
            "preview.tag_orig": "ORIGINAL",
            "preview.tag_edit": "TRADUCCIÓN / EDICIÓN ✏️",
            "preview.btn_load_video": "🎬 Cargar vídeo",
            "preview.video_filter": "Vídeos (*.mp4 *.mkv *.webm *.avi *.mov);;Todos los archivos (*.*)",
            "preview.save_dialog_title": "Guardar subtítulo editado",

            # Clean Page
            "clean.title": "Limpiar subtítulos",
            "clean.subtitle": "Elimina anuncios, enlaces y marcas de fansubs sin modificar los tiempos.",
            "clean.btn_clean": "🧹 Limpiar archivo ahora",

            # Convert Page
            "convert.title": "Conversión de formatos",
            "convert.subtitle": "Convierte entre SRT, VTT, ASS y TXT manteniendo la sincronización.",
            "convert.target_label": "Formato de destino:",
            "convert.btn_convert": "🔄 Convertir y guardar",

            # Batch Page
            "batch.title": "Procesamiento por lote",
            "batch.subtitle": "Traduce, limpia o convierte múltiples archivos en paralelo.",
            "batch.btn_add": "➕ Añadir subtítulos",
            "batch.btn_clear": "🗑️ Limpiar cola",
            "batch.col_file": "Archivo",
            "batch.col_size": "Tamaño",
            "batch.col_format": "Formato",
            "batch.col_status": "Estado",
            "batch.btn_start": "▶ Procesar todos los archivos",
            "batch.status_queued": "En cola",
            "batch.status_processing": "Procesando...",
            "batch.status_completed": "Completado",
            "batch.status_error": "Error: {err}",

            # Settings Page
            "settings.title": "Configuración de servicios",
            "settings.lang_card_title": "Idioma de la interfaz",
            "settings.lang_card_desc": "Selecciona el idioma de la aplicación o detecta automáticamente.",
            "settings.lang_auto": "🌐 Automático (Sistema)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "Clave de API para traducciones de alta fidelidad.",
            "settings.deepl_placeholder": "Clave API de DeepL (ej. 12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API",
            "settings.deepl_pro": "DeepL Pro API",
            "settings.openai_title": "OpenAI / Endpoint Compatible (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "API Key (opcional para endpoints locales)",
            "settings.openai_url_placeholder": "Base URL (ej. https://api.openai.com/v1 o http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "Modelo (ej. gpt-4o-mini)",
            "settings.btn_save": "💾 Guardar configuración",
            "settings.save_success": "¡Configuración guardada correctamente!",

            # Completed Page
            "completed.title": "Procesamiento completado",
            "completed.subtitle": "El archivo se ha procesado y guardado correctamente.",
            "completed.card_lines": "líneas procesadas",
            "completed.card_deleted": "líneas eliminadas",
            "completed.card_time": "tiempo total",
            "completed.btn_open_file": "📄 Abrir archivo",
            "completed.btn_open_folder": "📂 Ver en el explorador",
            "completed.btn_to_preview": "👁️ Ver en vista previa",
            "completed.summary_title": "Resumen de cambios",
            "completed.sum1": "✓ Limpieza de spam, URLs e IDs aplicada",
            "completed.sum2": "✓ Sincronización y estructura original conservadas",
            "completed.sum3": "✓ Archivo guardado correctamente",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "Versión Estable Multiplataforma • FFmpeg Estático Autónomo",
            "about.desc": "Aplicación de escritorio para traducir, editar, limpiar y quemar subtítulos en vídeo con sincronización en tiempo real y compatibilidad universal con .srt, .vtt, .ass y .txt.",
            "about.author_title": "Desarrollador",
            "about.author_role": "Desarrollador Principal y Arquitecto",
            "about.author_location": "Madrid, España",
            "about.btn_profile": "🌐 Perfil de GitHub",
            "about.btn_repo": "⭐ Repositorio",
            "about.license_title": "Licencia legal y Términos de uso",
            "about.license_name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International",
            "about.license_desc": "Este software se distribuye bajo la licencia CC BY-NC-SA 4.0. Eres libre de compartir y adaptar el material bajo los siguientes términos:",
            "about.perm_title": "PERMITIDO (USO LIBRE)",
            "about.perm_1": "✓ Compartir, copiar y redistribuir el código y la aplicación",
            "about.perm_2": "✓ Adaptar, remezclar, transformar y crear a partir del software",
            "about.perm_3": "✓ Uso personal, educativo y de investigación no comercial",
            "about.restr_title": "CONDICIONES Y RESTRICCIONES",
            "about.restr_1": "⚠️ Atribución (BY): Dar crédito al autor (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 No Comercial (NC): Prohibida la venta comercial o redistribución monetizada",
            "about.restr_3": "🔄 Compartir Igual (SA): Las obras derivadas deben llevar esta misma licencia CC",
            "about.btn_open_license": "📜 Abrir archivo LICENSE",
            "about.btn_web_deed": "🌐 Ver Términos Oficiales CC",

            # Burn In Dialog
            "burn.dialog_title": "Incrustar subtítulos en vídeo (Burn-In)",
            "burn.video_card_title": "Rutas de vídeo y salida",
            "burn.lbl_video_source": "Vídeo original:",
            "burn.lbl_output_file": "Vídeo de salida:",
            "burn.btn_browse": "Explorar...",
            "burn.style_card_title": "Estilo visual del subtítulo",
            "burn.lbl_font_size": "Tamaño tipográfico:",
            "burn.lbl_font_color": "Color del texto:",
            "burn.lbl_bg_box": "Caja de lectura:",
            "burn.lbl_font_family": "Tipografía:",
            "burn.color_white": "⚪ Blanco",
            "burn.color_yellow": "🟡 Amarillo",
            "burn.color_cyan": "🔵 Cian",
            "burn.box_none": "Ninguna (Solo contorno)",
            "burn.box_trans": "Caja semitransparente",
            "burn.box_solid": "Caja sólida",
            "burn.btn_burn": "🔥 Incrustar subtítulos en vídeo",
            "burn.btn_cancel": "Cancelar proceso",
            "burn.rendering_title": "Renderizando subtítulos...",
            "burn.encoding_status": "Codificando vídeo con FFmpeg...",
            "burn.speed": "Velocidad: {speed}",
            "burn.eta": "Tiempo restante: {eta}",
            "burn.btn_play": "▶ Reproducir vídeo",
            "burn.btn_folder": "📂 Abrir carpeta",
            "burn.btn_close": "Cerrar",

            # Alerts & Messages
            "alert.file_req_title": "Archivo requerido",
            "alert.file_req_desc": "Arrastra o selecciona un archivo de subtítulos primero.",
            "alert.no_subs_title": "Sin subtítulos",
            "alert.no_subs_desc": "No hay subtítulos disponibles para incrustar en el vídeo.\nCarga un archivo de subtítulos primero o procesa uno.",
            "alert.conv_success_title": "Conversión completada",
            "alert.conv_success_desc": "Archivo convertido y guardado en:\n{path}",
            "alert.conv_error_title": "Error en conversión",
            "alert.save_success_title": "Guardado con éxito",
            "alert.save_success_desc": "Subtítulo guardado en:\n{path}",
            "alert.burn_success_title": "Incrustación completada",
            "alert.burn_success_desc": "Vídeo renderizado con éxito con subtítulos incrustados:\n{path}",
        },

        # ------------------ PT (PORTUGUÊS) ------------------
        "pt": {
            # Navigation
            "nav.home": "Início",
            "nav.translate": "Traduzir",
            "nav.clean": "Limpar",
            "nav.convert": "Converter",
            "nav.batch": "Processamento em lote",
            "nav.settings": "Configurações",
            "nav.about": "Sobre",

            # Top bar
            "topbar.theme_tooltip": "Alternar modo claro / escuro",
            "topbar.lang_tooltip": "Alterar idioma da interface",
            "topbar.lang_auto": "🌐 Automático (Sistema)",

            # Home Page
            "home.title": "Traduzir Legendas",
            "home.subtitle": "Selecione seu arquivo, o idioma de destino e as opções de processamento.",
            "home.source_lang": "Idioma de origem",
            "home.target_lang": "Idioma de destino",
            "home.engine": "Motor de tradução",
            "home.clean_title": "Limpeza automática",
            "home.clean_desc": "Remove spam, URLs e anúncios",
            "home.format_title": "Preservar formato",
            "home.format_desc": "Mantém estilos e formatações (<i>, <b>, ASS)",
            "home.translate_title": "Traduzir texto",
            "home.translate_desc": "Traduz diálogos para o idioma de destino",
            "home.btn_process": "▶ Iniciar processamento",

            # Dropzone
            "dropzone.title": "Arraste o seu arquivo de legendas aqui",
            "dropzone.subtitle": "ou clique para selecionar",
            "dropzone.formats": "Formatos suportados: .srt, .ass, .vtt, .txt",
            "dropzone.size": "Tamanho: {size:.1f} KB",
            "dropzone.video_detected": "Vídeo detectado: {name}",
            "dropzone.replace_hint": "Clique ou arraste outro arquivo para substituir",
            "dropzone.dialog_title": "Selecionar legenda",
            "dropzone.filter": "Legendas (*.srt *.ass *.vtt *.txt);;Todos os arquivos (*.*)",

            # Preview / Translation Studio
            "preview.title": "Estúdio de Tradução",
            "preview.subtitle": "Pré-visualize vídeo, edite legendas linha por linha e sincronize.",
            "preview.btn_open": "📁 Abrir Legenda",
            "preview.btn_save": "💾 Salvar Legenda",
            "preview.btn_burn": "🔥 Gravar no Vídeo",
            "preview.search_placeholder": "🔍 Pesquisar no texto original ou tradução...",
            "preview.sub_count_zero": "0 legendas",
            "preview.sub_count_all": "Total: {total} legendas",
            "preview.sub_count_filtered": "Mostrando {visible} de {total}",
            "preview.autoscroll": "Rolar automaticamente com o vídeo",
            "preview.col_idx": "#",
            "preview.col_start": "Início",
            "preview.col_end": "Fim",
            "preview.col_orig": "Original",
            "preview.col_trans": "Tradução",
            "preview.btn_jump": "▶ Pular para o vídeo",
            "preview.tag_orig": "ORIGINAL",
            "preview.tag_edit": "TRADUÇÃO / EDIÇÃO ✏️",
            "preview.btn_load_video": "🎬 Carregar Vídeo",
            "preview.video_filter": "Vídeos (*.mp4 *.mkv *.webm *.avi *.mov);;Todos os arquivos (*.*)",
            "preview.save_dialog_title": "Salvar legenda editada",

            # Clean Page
            "clean.title": "Limpar Legendas",
            "clean.subtitle": "Remove anúncios, links e marcas de fansubs sem alterar os tempos.",
            "clean.btn_clean": "🧹 Limpar arquivo agora",

            # Convert Page
            "convert.title": "Conversão de Formatos",
            "convert.subtitle": "Converta entre SRT, VTT, ASS e TXT mantendo a sincronização.",
            "convert.target_label": "Formato de destino:",
            "convert.btn_convert": "🔄 Converter e salvar",

            # Batch Page
            "batch.title": "Processamento em Lote",
            "batch.subtitle": "Traduza, limpe ou converta múltiplos arquivos em paralelo.",
            "batch.btn_add": "➕ Adicionar Legendas",
            "batch.btn_clear": "🗑️ Limpar Fila",
            "batch.col_file": "Arquivo",
            "batch.col_size": "Tamanho",
            "batch.col_format": "Formato",
            "batch.col_status": "Estado",
            "batch.btn_start": "▶ Processar Todos os Arquivos",
            "batch.status_queued": "Na fila",
            "batch.status_processing": "Processando...",
            "batch.status_completed": "Concluído",
            "batch.status_error": "Erro: {err}",

            # Settings Page
            "settings.title": "Configurações de Serviços",
            "settings.lang_card_title": "Idioma da Interface",
            "settings.lang_card_desc": "Selecione o idioma da aplicação ou detecte automaticamente.",
            "settings.lang_auto": "🌐 Automático (Sistema)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "Chave de API para traduções de alta fidelidade.",
            "settings.deepl_placeholder": "Chave API DeepL (ex: 12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API",
            "settings.deepl_pro": "DeepL Pro API",
            "settings.openai_title": "OpenAI / Endpoint Compatível (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "Chave API (opcional para endpoints locais)",
            "settings.openai_url_placeholder": "URL Base (ex: https://api.openai.com/v1 ou http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "Modelo (ex: gpt-4o-mini)",
            "settings.btn_save": "💾 Salvar Configurações",
            "settings.save_success": "Configurações salvas com sucesso!",

            # Completed Page
            "completed.title": "Processamento Concluído",
            "completed.subtitle": "O arquivo foi processado e salvo com sucesso.",
            "completed.card_lines": "linhas processadas",
            "completed.card_deleted": "linhas removidas",
            "completed.card_time": "tempo total",
            "completed.btn_open_file": "📄 Abrir Arquivo",
            "completed.btn_open_folder": "📂 Mostrar no Explorador",
            "completed.btn_to_preview": "👁️ Ver no Estúdio",
            "completed.summary_title": "Resumo das Alterações",
            "completed.sum1": "✓ Limpeza de spam, URLs e marcadores aplicada",
            "completed.sum2": "✓ Sincronização e estrutura original preservadas",
            "completed.sum3": "✓ Arquivo salvo com sucesso",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "Versão Estável Multiplataforma • FFmpeg Estático Autônomo",
            "about.desc": "Aplicativo de desktop para traduzir, editar, limpar e embutir legendas em vídeo com sincronização em tempo real e suporte universal a .srt, .vtt, .ass e .txt.",
            "about.author_title": "Desenvolvedor",
            "about.author_role": "Desenvolvedor Principal e Arquiteto",
            "about.author_location": "Madri, Espanha",
            "about.btn_profile": "🌐 Perfil do GitHub",
            "about.btn_repo": "⭐ Repositório",
            "about.license_title": "Licença Legal e Termos de Uso",
            "about.license_name": "Creative Commons Atribuição-NãoComercial-CompartilhaIgual 4.0 Internacional",
            "about.license_desc": "Este software é distribuído sob a licença CC BY-NC-SA 4.0. Você é livre para compartilhar e adaptar o material sob os seguintes termos:",
            "about.perm_title": "PERMITIDO (USO LIVRE)",
            "about.perm_1": "✓ Compartilhar, copiar e redistribuir o código e a aplicação",
            "about.perm_2": "✓ Adaptar, remixar, transformar e criar a partir do software",
            "about.perm_3": "✓ Uso pessoal, educacional e de pesquisa não comercial",
            "about.restr_title": "CONDIÇÕES E RESTRIÇÕES",
            "about.restr_1": "⚠️ Atribuição (BY): Dar crédito ao autor (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 Não Comercial (NC): Proibida a venda ou redistribuição monetizada",
            "about.restr_3": "🔄 CompartilhaIgual (SA): Obras derivadas devem levar esta mesma licença CC",
            "about.btn_open_license": "📜 Abrir arquivo LICENSE",
            "about.btn_web_deed": "🌐 Ver Termos Oficiais CC",

            # Burn In Dialog
            "burn.dialog_title": "Embutir Legendas no Vídeo (Burn-In)",
            "burn.video_card_title": "Caminhos de Vídeo e Saída",
            "burn.lbl_video_source": "Vídeo original:",
            "burn.lbl_output_file": "Vídeo de saída:",
            "burn.btn_browse": "Procurar...",
            "burn.style_card_title": "Estilo Visual da Legenda",
            "burn.lbl_font_size": "Tamanho da fonte:",
            "burn.lbl_font_color": "Cor do texto:",
            "burn.lbl_bg_box": "Caixa de fundo:",
            "burn.lbl_font_family": "Família tipográfica:",
            "burn.color_white": "⚪ Branco",
            "burn.color_yellow": "🟡 Amarelo",
            "burn.color_cyan": "🔵 Ciano",
            "burn.box_none": "Nenhuma (Apenas contorno)",
            "burn.box_trans": "Caixa semitransparente",
            "burn.box_solid": "Caixa sólida opaca",
            "burn.btn_burn": "🔥 Gravar legendas no vídeo",
            "burn.btn_cancel": "Cancelar processo",
            "burn.rendering_title": "Renderizando legendas...",
            "burn.encoding_status": "Codificando vídeo com FFmpeg...",
            "burn.speed": "Velocidade: {speed}",
            "burn.eta": "Tempo restante: {eta}",
            "burn.btn_play": "▶ Reproduzir vídeo",
            "burn.btn_folder": "📂 Abrir pasta",
            "burn.btn_close": "Fechar",

            # Alerts & Messages
            "alert.file_req_title": "Arquivo obrigatório",
            "alert.file_req_desc": "Arraste ou selecione um arquivo de legendas primeiro.",
            "alert.no_subs_title": "Sem legendas",
            "alert.no_subs_desc": "Não há legendas disponíveis para embutir no vídeo.\nCarregue um arquivo primeiro ou processe um.",
            "alert.conv_success_title": "Conversão concluída",
            "alert.conv_success_desc": "Arquivo convertido e salvo em:\n{path}",
            "alert.conv_error_title": "Erro na conversão",
            "alert.save_success_title": "Salvo com sucesso",
            "alert.save_success_desc": "Legenda salva em:\n{path}",
            "alert.burn_success_title": "Gravação concluída",
            "alert.burn_success_desc": "Vídeo renderizado com sucesso com legendas embutidas:\n{path}",
        },

        # ------------------ DE (DEUTSCH) ------------------
        "de": {
            # Navigation
            "nav.home": "Startseite",
            "nav.translate": "Übersetzungsstudio",
            "nav.clean": "Bereinigen",
            "nav.convert": "Konvertieren",
            "nav.batch": "Stapelverarbeitung",
            "nav.settings": "Einstellungen",
            "nav.about": "Über",

            # Top bar
            "topbar.theme_tooltip": "Dunkel- / Hellmodus umschalten",
            "topbar.lang_tooltip": "Sprache der Benutzeroberfläche ändern",
            "topbar.lang_auto": "🌐 Automatisch (System)",

            # Home Page
            "home.title": "Untertitel Übersetzen",
            "home.subtitle": "Wählen Sie Datei, Zielsprache und Verarbeitungsoptionen.",
            "home.source_lang": "Ausgangssprache",
            "home.target_lang": "Zielsprache",
            "home.engine": "Übersetzungsdienst",
            "home.clean_title": "Automatische Bereinigung",
            "home.clean_desc": "Entfernt Spam, URLs und Werbung",
            "home.format_title": "Format beibehalten",
            "home.format_desc": "Behält Stile und Tags bei (<i>, <b>, ASS)",
            "home.translate_title": "Text übersetzen",
            "home.translate_desc": "Übersetzt Dialoge in die gewählte Zielsprache",
            "home.btn_process": "▶ Verarbeitung starten",

            # Dropzone
            "dropzone.title": "Untertiteldatei hierher ziehen",
            "dropzone.subtitle": "oder klicken zum Auswählen",
            "dropzone.formats": "Unterstützte Formate: .srt, .ass, .vtt, .txt",
            "dropzone.size": "Größe: {size:.1f} KB",
            "dropzone.video_detected": "Video erkannt: {name}",
            "dropzone.replace_hint": "Klicken oder andere Datei ziehen zum Ersetzen",
            "dropzone.dialog_title": "Untertitel auswählen",
            "dropzone.filter": "Untertitel (*.srt *.ass *.vtt *.txt);;Alle Dateien (*.*)",

            # Preview / Translation Studio
            "preview.title": "Übersetzungsstudio",
            "preview.subtitle": "Video vorschauen, Untertitel zeilenweise bearbeiten und synchronisieren.",
            "preview.btn_open": "📁 Untertitel öffnen",
            "preview.btn_save": "💾 Untertitel speichern",
            "preview.btn_burn": "🔥 In Video einbetten",
            "preview.search_placeholder": "🔍 In Original oder Übersetzung suchen...",
            "preview.sub_count_zero": "0 Untertitel",
            "preview.sub_count_all": "Gesamt: {total} Untertitel",
            "preview.sub_count_filtered": "Zeige {visible} von {total}",
            "preview.autoscroll": "Automatisch mit Video scrollen",
            "preview.col_idx": "#",
            "preview.col_start": "Start",
            "preview.col_end": "Ende",
            "preview.col_orig": "Original",
            "preview.col_trans": "Übersetzung",
            "preview.btn_jump": "▶ Zu Video springen",
            "preview.tag_orig": "ORIGINAL",
            "preview.tag_edit": "ÜBERSETZUNG / BEARBEITUNG ✏️",
            "preview.btn_load_video": "🎬 Video laden",
            "preview.video_filter": "Videos (*.mp4 *.mkv *.webm *.avi *.mov);;Alle Dateien (*.*)",
            "preview.save_dialog_title": "Bearbeiteten Untertitel speichern",

            # Clean Page
            "clean.title": "Untertitel Bereinigen",
            "clean.subtitle": "Entfernt Werbung, Links und Fansub-Spuren ohne Zeitänderung.",
            "clean.btn_clean": "🧹 Datei jetzt bereinigen",

            # Convert Page
            "convert.title": "Formatkonvertierung",
            "convert.subtitle": "Konvertieren zwischen SRT, VTT, ASS und TXT mit Synchronisation.",
            "convert.target_label": "Zielformat:",
            "convert.btn_convert": "🔄 Konvertieren und speichern",

            # Batch Page
            "batch.title": "Stapelverarbeitung",
            "batch.subtitle": "Mehrere Dateien parallel übersetzen, bereinigen oder konvertieren.",
            "batch.btn_add": "➕ Untertitel hinzufügen",
            "batch.btn_clear": "🗑️ Liste leeren",
            "batch.col_file": "Datei",
            "batch.col_size": "Größe",
            "batch.col_format": "Format",
            "batch.col_status": "Status",
            "batch.btn_start": "▶ Alle Dateien verarbeiten",
            "batch.status_queued": "In Warteschlange",
            "batch.status_processing": "Wird verarbeitet...",
            "batch.status_completed": "Abgeschlossen",
            "batch.status_error": "Fehler: {err}",

            # Settings Page
            "settings.title": "Diensteinstellungen",
            "settings.lang_card_title": "Sprache der Benutzeroberfläche",
            "settings.lang_card_desc": "Wählen Sie die Anzeigesprache oder automatische Erkennung.",
            "settings.lang_auto": "🌐 Automatisch (System)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "API-Schlüssel für hochpräzise Übersetzungen.",
            "settings.deepl_placeholder": "DeepL API-Schlüssel (z. B. 12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API",
            "settings.deepl_pro": "DeepL Pro API",
            "settings.openai_title": "OpenAI / Kompatibler Endpunkt (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "API-Schlüssel (optional für lokale Endpunkte)",
            "settings.openai_url_placeholder": "Basis-URL (z. B. https://api.openai.com/v1 oder http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "Modell (z. B. gpt-4o-mini)",
            "settings.btn_save": "💾 Einstellungen speichern",
            "settings.save_success": "Einstellungen erfolgreich gespeichert!",

            # Completed Page
            "completed.title": "Verarbeitung Abgeschlossen",
            "completed.subtitle": "Die Datei wurde erfolgreich verarbeitet und gespeichert.",
            "completed.card_lines": "verarbeitete Zeilen",
            "completed.card_deleted": "gelöschte Zeilen",
            "completed.card_time": "Gesamtzeit",
            "completed.btn_open_file": "📄 Datei öffnen",
            "completed.btn_open_folder": "📂 Im Explorer anzeigen",
            "completed.btn_to_preview": "👁️ In Vorschau ansehen",
            "completed.summary_title": "Zusammenfassung der Änderungen",
            "completed.sum1": "✓ Spam, URLs und Markierungen bereinigt",
            "completed.sum2": "✓ Original-Timing und Struktur beibehalten",
            "completed.sum3": "✓ Datei erfolgreich gespeichert",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "Stabile plattformübergreifende Version • Autonomes statisches FFmpeg",
            "about.desc": "Desktop-Anwendung zum Übersetzen, Bearbeiten, Bereinigen und Einbetten von Untertiteln in Videos mit Echtzeitsynchronisation.",
            "about.author_title": "Entwickler",
            "about.author_role": "Hauptentwickler & Softwarearchitekt",
            "about.author_location": "Madrid, Spanien",
            "about.btn_profile": "🌐 GitHub-Profil",
            "about.btn_repo": "⭐ Repository",
            "about.license_title": "Rechtliche Lizenz & Nutzungsbedingungen",
            "about.license_name": "Creative Commons Namensnennung-NichtKommerziell-Weitergabe unter gleichen Bedingungen 4.0 International",
            "about.license_desc": "Diese Software wird unter der CC BY-NC-SA 4.0-Lizenz vertrieben. Sie dürfen das Material unter folgenden Bedingungen teilen und bearbeiten:",
            "about.perm_title": "ERLAUBT (FREIE NUTZUNG)",
            "about.perm_1": "✓ Teilen, kopieren und weiterverbreiten des Codes und der App",
            "about.perm_2": "✓ Anpassen, remixen, transformieren und darauf aufbauen",
            "about.perm_3": "✓ Persönliche, bildungsbezogene und nicht-kommerzielle Forschung",
            "about.restr_title": "BEDINGUNGEN & EINSCHRÄNKUNGEN",
            "about.restr_1": "⚠️ Namensnennung (BY): Urheber angeben (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 Nicht-kommerziell (NC): Kommerzieller Verkauf ist untersagt",
            "about.restr_3": "🔄 Weitergabe unter gleichen Bedingungen (SA): Gleiche CC-Lizenz erforderlich",
            "about.btn_open_license": "📜 LICENSE-Datei öffnen",
            "about.btn_web_deed": "🌐 Offizielle CC-Bedingungen",

            # Burn In Dialog
            "burn.dialog_title": "Untertitel in Video einbetten (Hardsub)",
            "burn.video_card_title": "Video- und Ausgabepfade",
            "burn.lbl_video_source": "Quellvideo:",
            "burn.lbl_output_file": "Ausgabevideo:",
            "burn.btn_browse": "Durchsuchen...",
            "burn.style_card_title": "Untertitelstil",
            "burn.lbl_font_size": "Schriftgröße:",
            "burn.lbl_font_color": "Schriftfarbe:",
            "burn.lbl_bg_box": "Hintergrundbox:",
            "burn.lbl_font_family": "Schriftart:",
            "burn.color_white": "⚪ Weiß",
            "burn.color_yellow": "🟡 Gelb",
            "burn.color_cyan": "🔵 Cyan",
            "burn.box_none": "Keine (Nur Kontur)",
            "burn.box_trans": "Halbtransparente Box",
            "burn.box_solid": "Solide Box",
            "burn.btn_burn": "🔥 Untertitel jetzt einbetten",
            "burn.btn_cancel": "Vorgang abbrechen",
            "burn.rendering_title": "Untertitel werden gerendert...",
            "burn.encoding_status": "Video wird mit FFmpeg kodiert...",
            "burn.speed": "Geschwindigkeit: {speed}",
            "burn.eta": "Verbleibende Zeit: {eta}",
            "burn.btn_play": "▶ Video abspielen",
            "burn.btn_folder": "📂 Ordner öffnen",
            "burn.btn_close": "Schließen",

            # Alerts & Messages
            "alert.file_req_title": "Datei erforderlich",
            "alert.file_req_desc": "Bitte ziehen oder wählen Sie zuerst eine Untertiteldatei aus.",
            "alert.no_subs_title": "Keine Untertitel",
            "alert.no_subs_desc": "Keine Untertitel zum Einbetten verfügbar.\nBitte laden oder verarbeiten Sie zuerst eine Untertiteldatei.",
            "alert.conv_success_title": "Konvertierung abgeschlossen",
            "alert.conv_success_desc": "Datei konvertiert und gespeichert unter:\n{path}",
            "alert.conv_error_title": "Fehler bei Konvertierung",
            "alert.save_success_title": "Erfolgreich gespeichert",
            "alert.save_success_desc": "Untertitel gespeichert unter:\n{path}",
            "alert.burn_success_title": "Einbettung abgeschlossen",
            "alert.burn_success_desc": "Video erfolgreich mit festen Untertiteln gerendert:\n{path}",
        },

        # ------------------ IT (ITALIANO) ------------------
        "it": {
            # Navigation
            "nav.home": "Home",
            "nav.translate": "Traduci",
            "nav.clean": "Pulisci",
            "nav.convert": "Converti",
            "nav.batch": "Elaborazione in batch",
            "nav.settings": "Impostazioni",
            "nav.about": "Informazioni",

            # Top bar
            "topbar.theme_tooltip": "Alterna tema scuro / chiaro",
            "topbar.lang_tooltip": "Cambia lingua dell'interfaccia",
            "topbar.lang_auto": "🌐 Automatico (Sistema)",

            # Home Page
            "home.title": "Traduci Sottotitoli",
            "home.subtitle": "Seleziona il file, la lingua di destinazione e le opzioni di elaborazione.",
            "home.source_lang": "Lingua di origine",
            "home.target_lang": "Lingua di destinazione",
            "home.engine": "Motore di traduzione",
            "home.clean_title": "Pulizia automatica",
            "home.clean_desc": "Rimuove spam, URL e annunci",
            "home.format_title": "Mantieni formato",
            "home.format_desc": "Conserva stili e tag (<i>, <b>, ASS)",
            "home.translate_title": "Traduci testo",
            "home.translate_desc": "Traduci i dialoghi nella lingua di destinazione",
            "home.btn_process": "▶ Avvia elaborazione",

            # Dropzone
            "dropzone.title": "Trascina qui il file dei sottotitoli",
            "dropzone.subtitle": "o fai clic per selezionare",
            "dropzone.formats": "Formati supportati: .srt, .ass, .vtt, .txt",
            "dropzone.size": "Dimensione: {size:.1f} KB",
            "dropzone.video_detected": "Video rilevato: {name}",
            "dropzone.replace_hint": "Fai clic o trascina un altro file per sostituire",
            "dropzone.dialog_title": "Seleziona sottotitolo",
            "dropzone.filter": "Sottotitoli (*.srt *.ass *.vtt *.txt);;Tutti i file (*.*)",

            # Preview / Translation Studio
            "preview.title": "Studio di Traduzione",
            "preview.subtitle": "Anteprima video, modifica riga per riga e sincronizzazione.",
            "preview.btn_open": "📁 Apri Sottotitolo",
            "preview.btn_save": "💾 Salva Sottotitolo",
            "preview.btn_burn": "🔥 Incidi nel Video",
            "preview.search_placeholder": "🔍 Cerca nel testo originale o tradotto...",
            "preview.sub_count_zero": "0 sottotitoli",
            "preview.sub_count_all": "Totale: {total} sottotitoli",
            "preview.sub_count_filtered": "Mostrati {visible} di {total}",
            "preview.autoscroll": "Scorrimento automatico con video",
            "preview.col_idx": "#",
            "preview.col_start": "Inizio",
            "preview.col_end": "Fine",
            "preview.col_orig": "Originale",
            "preview.col_trans": "Traduzione",
            "preview.btn_jump": "▶ Salta al video",
            "preview.tag_orig": "ORIGINALE",
            "preview.tag_edit": "TRADUZIONE / MODIFICA ✏️",
            "preview.btn_load_video": "🎬 Carica Video",
            "preview.video_filter": "Video (*.mp4 *.mkv *.webm *.avi *.mov);;Tutti i file (*.*)",
            "preview.save_dialog_title": "Salva sottotitolo modificato",

            # Clean Page
            "clean.title": "Pulisci Sottotitoli",
            "clean.subtitle": "Rimuove annunci, link e crediti fansub senza modificare i tempi.",
            "clean.btn_clean": "🧹 Pulisci file adesso",

            # Convert Page
            "convert.title": "Conversione Formati",
            "convert.subtitle": "Converti tra SRT, VTT, ASS e TXT mantenendo la sincronizzazione.",
            "convert.target_label": "Formato di destinazione:",
            "convert.btn_convert": "🔄 Converti e salva",

            # Batch Page
            "batch.title": "Elaborazione in Batch",
            "batch.subtitle": "Traduci, pulisci o converti più file in parallelo.",
            "batch.btn_add": "➕ Aggiungi Sottotitoli",
            "batch.btn_clear": "🗑️ Svuota Coda",
            "batch.col_file": "File",
            "batch.col_size": "Dimensione",
            "batch.col_format": "Formato",
            "batch.col_status": "Stato",
            "batch.btn_start": "▶ Elabora Tutti i File",
            "batch.status_queued": "In coda",
            "batch.status_processing": "In elaborazione...",
            "batch.status_completed": "Completato",
            "batch.status_error": "Errore: {err}",

            # Settings Page
            "settings.title": "Impostazioni Servizi",
            "settings.lang_card_title": "Lingua dell'Interfaccia",
            "settings.lang_card_desc": "Seleziona la lingua dell'applicazione o rileva automaticamente.",
            "settings.lang_auto": "🌐 Automatico (Sistema)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "Chiave API per traduzioni di alta fedeltà.",
            "settings.deepl_placeholder": "Chiave API DeepL (es: 12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API",
            "settings.deepl_pro": "DeepL Pro API",
            "settings.openai_title": "OpenAI / Endpoint Compatibile (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "Chiave API (opzionale per endpoint locali)",
            "settings.openai_url_placeholder": "URL di base (es. https://api.openai.com/v1 o http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "Modello (es. gpt-4o-mini)",
            "settings.btn_save": "💾 Salva Impostazioni",
            "settings.save_success": "Impostazioni salvate con successo!",

            # Completed Page
            "completed.title": "Elaborazione Completata",
            "completed.subtitle": "Il file è stato elaborato e salvato correttamente.",
            "completed.card_lines": "righe elaborate",
            "completed.card_deleted": "righe rimosse",
            "completed.card_time": "tempo totale",
            "completed.btn_open_file": "📄 Apri File",
            "completed.btn_open_folder": "📂 Mostra nel File Manager",
            "completed.btn_to_preview": "👁️ Vedi in Studio",
            "completed.summary_title": "Riepilogo Modifiche",
            "completed.sum1": "✓ Pulizia di spam, URL e marcatori applicata",
            "completed.sum2": "✓ Sincronizzazione e struttura originale preservate",
            "completed.sum3": "✓ File salvato con successo",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "Versione Stabile Multipiattaforma • FFmpeg Statico Autonomo",
            "about.desc": "Applicazione desktop per tradurre, modificare, pulire e incidere sottotitoli su video con sincronizzazione in tempo reale e supporto a .srt, .vtt, .ass e .txt.",
            "about.author_title": "Sviluppatore",
            "about.author_role": "Sviluppatore Principale e Architetto",
            "about.author_location": "Madrid, Spagna",
            "about.btn_profile": "🌐 Profilo GitHub",
            "about.btn_repo": "⭐ Repository",
            "about.license_title": "Licenza Legale e Termini d'Uso",
            "about.license_name": "Creative Commons Attribuzione - Non commerciale - Condividi allo stesso modo 4.0 Internazionale",
            "about.license_desc": "Questo software è distribuito sotto licenza CC BY-NC-SA 4.0. Sei libero di condividere e adattare il materiale alle seguenti condizioni:",
            "about.perm_title": "CONSENTITO (USO LIBERO)",
            "about.perm_1": "✓ Condividere, copiare e ridistribuire il codice e l'applicazione",
            "about.perm_2": "✓ Adattare, remixare, trasformare e sviluppare sul software",
            "about.perm_3": "✓ Uso personale, educativo e di ricerca non commerciale",
            "about.restr_title": "CONDIZIONI E RESTRIZIONI",
            "about.restr_1": "⚠️ Attribuzione (BY): Dare credito all'autore (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 Non commerciale (NC): Vendita o ridistribuzione monetizzata vietata",
            "about.restr_3": "🔄 Condividi allo stesso modo (SA): Le opere derivate devono avere questa stessa licenza",
            "about.btn_open_license": "📜 Apri file LICENSE",
            "about.btn_web_deed": "🌐 Visualizza Termini Ufficiali CC",

            # Burn In Dialog
            "burn.dialog_title": "Incidi Sottotitoli nel Video (Hardsub)",
            "burn.video_card_title": "Percorsi Video e di Output",
            "burn.lbl_video_source": "Video originale:",
            "burn.lbl_output_file": "Video finale:",
            "burn.btn_browse": "Sfoglia...",
            "burn.style_card_title": "Stile Visivo dei Sottotitoli",
            "burn.lbl_font_size": "Dimensione carattere:",
            "burn.lbl_font_color": "Colore del testo:",
            "burn.lbl_bg_box": "Riquadro di sfondo:",
            "burn.lbl_font_family": "Carattere:",
            "burn.color_white": "⚪ Bianco",
            "burn.color_yellow": "🟡 Giallo",
            "burn.color_cyan": "🔵 Ciano",
            "burn.box_none": "Nessuno (Solo contorno)",
            "burn.box_trans": "Riquadro semitrasparente",
            "burn.box_solid": "Riquadro solido opaco",
            "burn.btn_burn": "🔥 Incidi sottotitoli nel video",
            "burn.btn_cancel": "Annulla processo",
            "burn.rendering_title": "Rendering dei sottotitoli in corso...",
            "burn.encoding_status": "Codifica video con FFmpeg...",
            "burn.speed": "Velocità: {speed}",
            "burn.eta": "Tempo rimanente: {eta}",
            "burn.btn_play": "▶ Riproduci video",
            "burn.btn_folder": "📂 Apri cartella",
            "burn.btn_close": "Chiudi",

            # Alerts & Messages
            "alert.file_req_title": "File richiesto",
            "alert.file_req_desc": "Trascina o seleziona prima un file di sottotitoli.",
            "alert.no_subs_title": "Nessun sottotitolo",
            "alert.no_subs_desc": "Nessun sottotitolo disponibile da incidere nel video.\nCarica prima un file o elaborane uno.",
            "alert.conv_success_title": "Conversione completata",
            "alert.conv_success_desc": "File convertito e salvato in:\n{path}",
            "alert.conv_error_title": "Errore di conversione",
            "alert.save_success_title": "Salvato con successo",
            "alert.save_success_desc": "Sottotitolo salvato in:\n{path}",
            "alert.burn_success_title": "Incisione completata",
            "alert.burn_success_desc": "Video renderizzato con successo con sottotitoli incisi:\n{path}",
        },

        # ------------------ ZH-CN (简体中文) ------------------
        "zh-CN": {
            # Navigation
            "nav.home": "首页",
            "nav.translate": "翻译工作室",
            "nav.clean": "清理",
            "nav.convert": "格式转换",
            "nav.batch": "批量处理",
            "nav.settings": "设置",
            "nav.about": "关于",

            # Top bar
            "topbar.theme_tooltip": "切换深色 / 浅色主题",
            "topbar.lang_tooltip": "切换界面语言",
            "topbar.lang_auto": "🌐 自动检测 (系统)",

            # Home Page
            "home.title": "翻译字幕",
            "home.subtitle": "选择您的字幕文件、目标语言及处理选项。",
            "home.source_lang": "源语言",
            "home.target_lang": "目标语言",
            "home.engine": "翻译引擎",
            "home.clean_title": "自动清理",
            "home.clean_desc": "清除垃圾广告、链接与字幕组水印",
            "home.format_title": "保留格式",
            "home.format_desc": "保持原有样式和标签 (<i>, <b>, ASS)",
            "home.translate_title": "翻译文本",
            "home.translate_desc": "将对话内容翻译至目标语言",
            "home.btn_process": "▶ 开始处理",

            # Dropzone
            "dropzone.title": "将字幕文件拖放至此处",
            "dropzone.subtitle": "或点击浏览文件",
            "dropzone.formats": "支持格式：.srt, .ass, .vtt, .txt",
            "dropzone.size": "大小：{size:.1f} KB",
            "dropzone.video_detected": "检测到视频：{name}",
            "dropzone.replace_hint": "点击或拖放其他文件以替换",
            "dropzone.dialog_title": "选择字幕文件",
            "dropzone.filter": "字幕文件 (*.srt *.ass *.vtt *.txt);;所有文件 (*.*)",

            # Preview / Translation Studio
            "preview.title": "翻译工作室",
            "preview.subtitle": "视频实时预览、逐行精准编辑与轴音画同步。",
            "preview.btn_open": "📁 打开字幕",
            "preview.btn_save": "💾 保存字幕",
            "preview.btn_burn": "🔥 压制进视频",
            "preview.search_placeholder": "🔍 在原文或译文中搜索关键词...",
            "preview.sub_count_zero": "0 条字幕",
            "preview.sub_count_all": "共 {total} 条字幕",
            "preview.sub_count_filtered": "显示 {visible} / {total} 条",
            "preview.autoscroll": "随视频播放自动滚动",
            "preview.col_idx": "#",
            "preview.col_start": "起始时间",
            "preview.col_end": "结束时间",
            "preview.col_orig": "原文",
            "preview.col_trans": "译文",
            "preview.btn_jump": "▶ 跳转至视频对应位置",
            "preview.tag_orig": "原文",
            "preview.tag_edit": "译文 / 编辑 ✏️",
            "preview.btn_load_video": "🎬 加载视频",
            "preview.video_filter": "视频文件 (*.mp4 *.mkv *.webm *.avi *.mov);;所有文件 (*.*)",
            "preview.save_dialog_title": "保存已编辑的字幕",

            # Clean Page
            "clean.title": "清理字幕",
            "clean.subtitle": "在不改变时间轴的前提下，智能去除广告、链接与字幕组标记。",
            "clean.btn_clean": "🧹 立即清理文件",

            # Convert Page
            "convert.title": "格式转换",
            "convert.subtitle": "在 SRT、VTT、ASS 和 TXT 之间互转并保持时间轴同步。",
            "convert.target_label": "目标格式：",
            "convert.btn_convert": "🔄 转换并保存",

            # Batch Page
            "batch.title": "批量处理",
            "batch.subtitle": "并行批量翻译、清理或转换多个字幕文件。",
            "batch.btn_add": "➕ 添加字幕文件",
            "batch.btn_clear": "🗑️ 清空列表",
            "batch.col_file": "文件名",
            "batch.col_size": "大小",
            "batch.col_format": "格式",
            "batch.col_status": "处理状态",
            "batch.btn_start": "▶ 开始批量处理全部文件",
            "batch.status_queued": "排队中",
            "batch.status_processing": "处理中...",
            "batch.status_completed": "已完成",
            "batch.status_error": "错误：{err}",

            # Settings Page
            "settings.title": "服务与设置",
            "settings.lang_card_title": "界面显示语言",
            "settings.lang_card_desc": "选择应用程序的语言，或设为自动根据系统语言切换。",
            "settings.lang_auto": "🌐 自动检测 (系统)",
            "settings.deepl_title": "DeepL API",
            "settings.deepl_desc": "用于高品质神经网络翻译的 API 密钥。",
            "settings.deepl_placeholder": "DeepL API 密钥 (例如：12345678-abcd...)",
            "settings.deepl_free": "DeepL Free API (免费版)",
            "settings.deepl_pro": "DeepL Pro API (专业版)",
            "settings.openai_title": "OpenAI / 兼容端点 (Ollama, OpenRouter)",
            "settings.openai_key_placeholder": "API 密钥 (本地模型端点可选填)",
            "settings.openai_url_placeholder": "基础 URL (例如：https://api.openai.com/v1 或 http://localhost:11434/v1)",
            "settings.openai_model_placeholder": "模型名称 (例如：gpt-4o-mini)",
            "settings.btn_save": "💾 保存设置",
            "settings.save_success": "设置已成功保存！",

            # Completed Page
            "completed.title": "处理完成",
            "completed.subtitle": "字幕文件已处理完毕并成功保存至本地。",
            "completed.card_lines": "已处理行数",
            "completed.card_deleted": "已清理无效行",
            "completed.card_time": "总耗时",
            "completed.btn_open_file": "📄 打开文件",
            "completed.btn_open_folder": "📂 打开所在目录",
            "completed.btn_to_preview": "👁️ 在工作区预览",
            "completed.summary_title": "变更摘要",
            "completed.sum1": "✓ 广告、URL 与多余标记已清除",
            "completed.sum2": "✓ 原始时间轴与对话结构完好保留",
            "completed.sum3": "✓ 文件已成功写入磁盘",

            # About Page
            "about.title": "SRT4U - Subtitle Processor",
            "about.version_pill": "v1.0.0",
            "about.status": "跨平台稳定版 • 内置自主静态 FFmpeg 引擎",
            "about.desc": "专为桌面端设计的字幕处理工具，集翻译、编辑、清理、时间同步以及视频硬字幕压制于一体，原生兼容 .srt、.vtt、.ass 与 .txt。",
            "about.author_title": "开发者",
            "about.author_role": "核心开发者与系统架构师",
            "about.author_location": "西班牙马德里",
            "about.btn_profile": "🌐 GitHub 主页",
            "about.btn_repo": "⭐ 开源仓库",
            "about.license_title": "法律许可与使用条款",
            "about.license_name": "知识共享 署名-非商业性使用-相同方式共享 4.0 国际 (CC BY-NC-SA 4.0)",
            "about.license_desc": "本软件基于 CC BY-NC-SA 4.0 协议分发。在遵守以下条款的前提下，您可以自由共享与修改本程序：",
            "about.perm_title": "允许的使用方式 (自由使用)",
            "about.perm_1": "✓ 自由分享、复制和分发代码与应用程序",
            "about.perm_2": "✓ 自由修改、混合、转换并在此基础上进行二次开发",
            "about.perm_3": "✓ 个人非商业使用、教育和学术研究",
            "about.restr_title": "使用条件与限制",
            "about.restr_1": "⚠️ 署名 (BY)：必须注明原作者姓名 (Miguel Ángel Rodríguez Dalí)",
            "about.restr_2": "🚫 非商业性 (NC)：严禁将本软件或衍生版本用于商业销售与盈利",
            "about.restr_3": "🔄 相同方式共享 (SA)：基于本项目的衍生作品必须采用相同的 CC 协议分发",
            "about.btn_open_license": "📜 打开本地 LICENSE 文件",
            "about.btn_web_deed": "🌐 查看 CC 协议官方详情",

            # Burn In Dialog
            "burn.dialog_title": "压制字幕到视频 (硬字幕 / Hardsub)",
            "burn.video_card_title": "视频与输出路径",
            "burn.lbl_video_source": "原始视频：",
            "burn.lbl_output_file": "导出视频：",
            "burn.btn_browse": "浏览...",
            "burn.style_card_title": "字幕视觉样式",
            "burn.lbl_font_size": "字号大小：",
            "burn.lbl_font_color": "字体颜色：",
            "burn.lbl_bg_box": "背景样式：",
            "burn.lbl_font_family": "字体系列：",
            "burn.color_white": "⚪ 白色",
            "burn.color_yellow": "🟡 黄色",
            "burn.color_cyan": "🔵 青色",
            "burn.box_none": "无背景 (仅外描边)",
            "burn.box_trans": "半透明舒适底框",
            "burn.box_solid": "纯色不透明背景",
            "burn.btn_burn": "🔥 开始压制字幕到视频",
            "burn.btn_cancel": "取消压制",
            "burn.rendering_title": "正在渲染字幕...",
            "burn.encoding_status": "正在使用 FFmpeg 编码视频...",
            "burn.speed": "编码速度：{speed}",
            "burn.eta": "预计剩余时间：{eta}",
            "burn.btn_play": "▶ 播放视频",
            "burn.btn_folder": "📂 打开文件夹",
            "burn.btn_close": "关闭",

            # Alerts & Messages
            "alert.file_req_title": "缺少文件",
            "alert.file_req_desc": "请先拖放或选择一个字幕文件。",
            "alert.no_subs_title": "暂无字幕",
            "alert.no_subs_desc": "当前没有可用于压制进视频的字幕内容。\n请先打开或处理一个字幕文件。",
            "alert.conv_success_title": "格式转换成功",
            "alert.conv_success_desc": "文件已转换并保存至：\n{path}",
            "alert.conv_error_title": "转换出错",
            "alert.save_success_title": "保存成功",
            "alert.save_success_desc": "字幕已保存至：\n{path}",
            "alert.burn_success_title": "字幕压制完成",
            "alert.burn_success_desc": "已成功导出带有硬字幕的视频文件：\n{path}",
        },
    }

    def __init__(self, config_service: Optional[ConfigService] = None, parent=None):
        super().__init__(parent)
        self.config_service = config_service or ConfigService()
        self._current_lang = "es"
        self._load_initial_language()

    @classmethod
    def get_instance(cls, config_service: Optional[ConfigService] = None) -> "I18nService":
        if cls._instance is None:
            cls._instance = cls(config_service=config_service)
        return cls._instance

    def detect_system_language(self) -> str:
        """
        Detecta el idioma del sistema operativo usando QLocale y variables de entorno.
        Retorna uno de los códigos soportados ('es', 'en', 'pt', 'de', 'it', 'zh-CN').
        Si no coincide, usa 'en' como fallback internacional.
        """
        locale_str = ""
        try:
            locale_str = QLocale.system().name().lower()
        except Exception:
            pass

        if not locale_str:
            for env_var in ["LC_ALL", "LC_MESSAGES", "LANG"]:
                val = os.environ.get(env_var, "")
                if val:
                    locale_str = val.lower()
                    break

        if locale_str.startswith("es"):
            return "es"
        elif locale_str.startswith("pt"):
            return "pt"
        elif locale_str.startswith("de"):
            return "de"
        elif locale_str.startswith("it"):
            return "it"
        elif locale_str.startswith("zh"):
            return "zh-CN"
        else:
            return "en"

    def _load_initial_language(self):
        saved_lang = self.config_service.get("ui_language", "auto")
        if not saved_lang or saved_lang == "auto" or saved_lang not in self.SUPPORTED_LANGUAGES:
            self._current_lang = self.detect_system_language()
        else:
            self._current_lang = saved_lang

    @property
    def supported_languages(self) -> Dict[str, Dict[str, str]]:
        return self.SUPPORTED_LANGUAGES

    @property
    def current_language(self) -> str:
        return self._current_lang

    def get_configured_language(self) -> str:
        """Retorna 'auto' o el código específico guardado en config."""
        return self.config_service.get("ui_language", "auto")

    def set_language(self, lang_code: str, save_to_config: bool = True):
        """
        Establece el idioma activo ('auto' o código específico) y emite language_changed.
        """
        if lang_code == "auto":
            active = self.detect_system_language()
            if save_to_config:
                self.config_service.set("ui_language", "auto")
        elif lang_code in self.SUPPORTED_LANGUAGES:
            active = lang_code
            if save_to_config:
                self.config_service.set("ui_language", lang_code)
        else:
            active = "en"

        old_lang = self._current_lang
        self._current_lang = active
        if old_lang != active:
            self.language_changed.emit(active)

    def t(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        Obtiene la traducción para una clave dada en el idioma activo.
        Fallback en cascada: idioma activo -> inglés (en) -> español (es) -> default -> key.
        """
        catalog = self.TRANSLATIONS.get(self._current_lang, {})
        val = catalog.get(key)

        if val is None and self._current_lang != "en":
            val = self.TRANSLATIONS.get("en", {}).get(key)

        if val is None and self._current_lang != "es":
            val = self.TRANSLATIONS.get("es", {}).get(key)

        if val is None:
            val = default if default is not None else key

        if kwargs:
            try:
                return val.format(**kwargs)
            except Exception:
                return val

        return val


def get_i18n(config_service: Optional[ConfigService] = None) -> I18nService:
    """Función de acceso global al servicio de i18n."""
    return I18nService.get_instance(config_service=config_service)


def t(key: str, default: Optional[str] = None, **kwargs) -> str:
    """Acceso rápido a traducción i18n."""
    return get_i18n().t(key, default, **kwargs)
