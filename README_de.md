<div align="center">
  <img src="assets/icon.png" alt="SRT4U-Logo" height="96" />
</div>

# SRT4U - Subtitle Processor

[![License: GPL-3.0-only](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

[**English**](README.md) | [**Español**](README_es.md) | **Deutsch** | [**Français**](README_fr.md) | [**Italiano**](README_it.md) | [**中文**](README_zh.md)

Desktop-App zum Übersetzen, Bearbeiten, Bereinigen und Konvertieren von Untertiteldateien (`.srt`, `.vtt`, `.ass`/`.ssa`, `.txt`) mit einem echtzeit-synchronisierten Videoplayer und direktem Video-Burn-in-Export.

Aktuelles stabiles Release: **[v1.4.10](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.10)**. Details siehe [RELEASE_NOTES.md](RELEASE_NOTES.md).

![SRT4U-Vorschau](assets/preview_en.png)

---

## Funktionen

- **Mehrsprachige Oberfläche (i18n)**:
  - Automatische Systemspracherkennung beim Start via `QLocale`.
  - Live-Sprachwechsel zur Laufzeit ohne App-Neustart.
  - 7 unterstützte Sprachen: Englisch (`en`), Spanisch (`es`), Portugiesisch (`pt`), Deutsch (`de`), Italienisch (`it`), Französisch (`fr`) und vereinfachtes Chinesisch (`zh-CN`).
  - Dualer Zugang: Schnellumschalter in der oberen Leiste und persistente Auswahl in den Einstellungen.
- **Video-Burn-In (Hardsub-Export)**:
  - Bettet Untertitel permanent in Videodateien ein (`.mp4`, `.mkv`, `.webm` usw.).
  - Visuelle Anpassung: Schriftgröße, Farbe (Weiß, Gelb, Cyan) und Leseboxen (halbtransparent, solide oder Rahmenkontur).
  - Adaptives Auflösungsrendering: Untertitel skalieren proportional zur Videohöhe (von 480p bis 4K und vertikale Reels/TikTok).
  - Automatischer Überlappungsbereiniger: Verhindert, dass sich überlappende Untertitel-Timecodes auf dem Bildschirm überlagern.
  - Echtzeit-Fortschrittsmodal mit Kodiergeschwindigkeit (x), verstrichener Zeit und ETA.
- **Interaktives Übersetzungsstudio**:
  - Live-Seite-an-Seite-Karteneditor zur zeilenweisen Prüfung und Verfeinerung von Übersetzungen.
  - Synchronisiert mit dem eingebauten Videoplayer (jeden Untertitel anklicken, um zu diesem Videoframe zu springen).
  - Cues sofort suchen und filtern.
- **Übersetzungs-Engines**:
  - Google Translate: Eingebaute kostenlose Stufe ohne Setup oder API-Schlüssel.
  - DeepL: Free- und Pro-API-Schlüsselunterstützung.
  - OpenAI / Lokale LLMs: Kompatibel mit OpenAI-, Ollama- und OpenRouter-Endpunkten.
- **Automatisierter Bereiniger**: Entfernt Telegram-Kanäle (`t.me`), URLs, Fansub-Credits, Werbung und musikalische Marker (`♪`), wobei gültige Dialoge und Formatierungstags (`<i>`, `<b>`, ASS-Stile) erhalten bleiben.
- **Formatkonverter**: Bidirektionale Konvertierung zwischen `.srt`, `.vtt`, `.ass` und Klartext-`.txt`.
- **Batch-Verarbeitung**: Mehrere Dateien in Warteschlange mit Fortschrittstracking pro Datei.
- **Untertitelanalytik & deterministisches QA**: gruppierte Inhalts-/Timing-/Qualitätsmetriken plus regelbasierte Validierung (`analyze`/`qa`, JSON/CSV).
- **Übersetzungsbenchmarks**: reproduzierbarer Anbietervergleich mit JSON/CSV-Berichten und Offline-Analyse-Notebook.
- **Lokaler SQLite-Verlauf**: Jede Ausführung mit aggregierten Metriken aufgezeichnet (Verlaufsseite, `history`-CLI); keine Texte, Schlüssel oder Medien gespeichert.
- **Lokale REST-API** (optionales `[api]`-Extra): `/api/v1` mit Analyse-, QA-, Übersetzungs-/Verarbeitungs-/Transkriptions-/Pipeline-Jobs, Verlauf, Benchmarks, OpenAPI-Docs — bindet standardmäßig an localhost, keine Authentifizierung.
- **Lokale Whisper-Transkription** (optionales `[transcription]`-Extra): Audio/Video → Untertitel für Analytik, QA, Bereinigung, Übersetzung, Burn-in. Modelle sind nicht gebündelt; sie laden beim ersten Gebrauch herunter.
- **Ende-zu-Ende-Medienpipeline**: `srt4u pipeline` / Pipeline-Seite / `POST /api/v1/pipeline` verkettet Transkription → Bereinigung → Analytik → QA → optionale Übersetzung → finales QA → Export → optionales Burn-in, mit Fehlern pro Stufe und kooperativer (Best-Effort-)Abbrechung: wartende Jobs werden verworfen, laufende beendet und ihr Ergebnis verworfen.
- **Headless-CLI**: Batches verarbeiten, Untertitelmetriken analysieren und deterministisches QA mit JSON/CSV-Exporten ohne PyQt6-Start.
- **Parallele Ausführung**: Multithread-Blockübersetzung zur Beschleunigung großer Untertiteldateien.
- **Dunkles / helles Glass-Design**: Moderne Glassmorphism-UI mit sofortigem Designwechsel.

---

## Installation & Ausführung

### Anforderungen
- Python 3.10 oder höher
- `pip`

### Aus dem Quellcode ausführen

```bash
# Repository klonen
git clone https://github.com/marodriguezd/SRT4U-Subtitle-Processor.git
cd SRT4U-Subtitle-Processor

# Virtuelle Umgebung erstellen und aktivieren
python -m venv .venv
source .venv/bin/activate  # Unter Windows: .venv\Scripts\activate

# Abhängigkeiten installieren (Source-Checkout-Pfad: derselbe Basisstack wie `pip install .`)
pip install -r requirements.txt

# Desktop-Anwendung starten
python main.py

# Ohne UI verarbeiten
python -m application.cli process input.srt --output output.srt --clean
```

### Optionale Extras

```bash
pip install ".[api]"            # lokale REST-API: srt4u serve (/api/v1, OpenAPI; standardmäßig localhost, keine Auth)
pip install ".[transcription]"  # lokales Whisper: srt4u transcribe / pipeline media
pip install ".[dev]"            # pytest + ruff für Mitwirkende
```

> [!NOTE]
> Die Basisinstallation (`pip install .`) enthält den GUI- und CLI-Stack (PyQt6 +
> `deep-translator`) sowie Analytik, QA, Übersetzung, Verlauf und die
> Pipeline für Untertitelinputs. `requirements.txt` spiegelt diese Basis-
> anforderungen für Source-Checkouts und CI. Die Extras `[api]`, `[transcription]` und
> `[dev]` fügen FastAPI, `faster-whisper` und Entwicklungswerkzeuge hinzu. Whisper-
> Modelle sind nicht gebündelt; sie laden beim ersten Gebrauch mit vorheriger Ankündigung
> herunter (`SRT4U_WHISPER_MODEL_DIR` verlagert den Cache). Burn-in erfordert FFmpeg; CI-
> Builds bündeln ein FFmpeg-Executable, während Source-Installationen ein nutzbares FFmpeg
> auf `PATH` oder im Anwendungsbundle benötigen.

### 60-Sekunden-Schnellstart

```bash
python -m application.cli analyze input.srt --json
python -m application.cli qa input.srt --strict
python -m application.cli process input.srt --clean --translate --target en
python -m application.cli transcribe clip.mp4 --model small --language auto
python -m application.cli pipeline clip.mp4 --translate --target en -o out.srt --stats-json
python -m application.cli serve  # Docs unter http://127.0.0.1:8000/docs
```

Architektur (GUI/CLI/API → Dienste → Anbieter/SQLite/FFmpeg) und Bereichs-
anleitungen: [docs/cli.md](docs/cli.md), [docs/api.md](docs/api.md),
[docs/transcription.md](docs/transcription.md), [docs/pipeline.md](docs/pipeline.md),
[docs/database.md](docs/database.md), [docs/tech-debt.md](docs/tech-debt.md).

### Vorgefertigte Binärdateien

Das aktuelle stabile Release ist **[v1.4.10](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.10)** (kein Prerelease). GitHub Actions baut und hängt diese Assets für jeden stabilen `v*`-Tag an:

| Asset | Plattform | Architektur |
|---|---|---|
| [`SRT4U-Windows-x64.exe`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Windows-x64.exe) | Windows 10/11 | x86_64 |
| [`SRT4U-Linux-x86_64.AppImage`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Linux-x86_64.AppImage) | Linux | x86_64 |
| [`SRT4U-Linux-x86_64.tar.gz`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Linux-x86_64.tar.gz) | Linux | x86_64 |
| [`SRT4U-macOS.dmg`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-macOS.dmg) | macOS (Apple Silicon) | **nur arm64** — startet nicht auf Intel-Macs |
| [`checksums.txt`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/checksums.txt) | SHA-256-Prüfsummen der obigen Assets | — |

Die CI-Builds bündeln ein versionsgepinntes statisches FFmpeg-Executable, sodass Burn-in
out of the box funktioniert; Plattform-Laufzeitbibliotheksanforderungen gelten weiterhin.
Source-Installationen (voriger Abschnitt) benötigen ein nutzbares FFmpeg auf `PATH` für Burn-in.

---

## Headless-CLI

Die CLI nutzt `SubtitleService` wieder, um ohne Erzeugung einer Qt-Anwendung zu bereinigen, zu übersetzen, Formate zu konvertieren und Verzeichnisse in Batches zu verarbeiten. Nach Paketinstallation `srt4u process` ausführen; aus einem Checkout `python -m application.cli process` nutzen. JSON-Presets und Optionen wie `--translate --source auto --target es --engine ollama` werden unterstützt. Siehe [docs/cli.md](docs/cli.md) für Beispiele, Preset-Schlüssel und Ausgabeverhalten.

## Analytik & QA

`analyze` berechnet gruppierte Inhalts-, Timing-, Qualitäts- und Verarbeitungsmetriken. `qa` meldet deterministische Untertitelprobleme mit konfigurierbaren Schwellen. Beide Befehle unterstützen JSON; Analytik kann auch nach CSV exportiert werden. Siehe [docs/analytics.md](docs/analytics.md) für Metrikdefinitionen, Regeldefaults und CLI-Exportbeispiele.

## Übersetzungsanbieter & Metriken

`TranslationService` dispatched über `ProviderRegistry` an `Google`, `DeepL` oder den OpenAI-kompatiblen Endpunkt (`openai`-, `llm`- und `ollama`-Aliase teilen sich die Implementierung; der angeforderte Anbieter bleibt in den Metriken erhalten). Fehler sind normalisiert (`error_type`), Retries sind opt-in und Fallbacks explizit, konfigurierbar und zyklenfest. `translate_with_metrics()` gibt `TranslationResult` mit JSON-serialisierbarem `TranslationMetrics` zurück; die CLI druckt sie mit `--stats` oder `--stats-json`, und `estimated_cost` bleibt `null` — keine erfundenen Tarife.

`benchmark` fährt einen versionierten Datensatz gegen mehrere Anbieter über N Läufe und exportiert JSON/CSV für Offline-Analyse (`notebooks/benchmark_analysis.ipynb` + `analysis/benchmark_analysis.py`). Ausführungen werden in einem lokalen SQLite-Verlauf aufgezeichnet (`history`-CLI, Verlaufsseite, `--store` für Benchmarks): nur aggregierte Metriken — niemals Texte, Schlüssel oder Medien gespeichert.

Vertiefungen: [docs/providers.md](docs/providers.md), [docs/benchmarking.md](docs/benchmarking.md), [docs/benchmark_analysis.md](docs/benchmark_analysis.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/transcription.md](docs/transcription.md) und [docs/pipeline.md](docs/pipeline.md).

## Tests ausführen

Die Testsuite deckt Parsing, Bereinigung, formatübergreifende Konvertierung, freie Übersetzung, UI-Flows, UI-Layoutregression (Clipped-Text-Erkennung in 6 Sprachen × 2 Designs) und Dialoggeometrie-Invarianten ab:

```bash
pytest tests/ -m "not network"  # kein Netzwerk, Schlüssel oder Whisper-Modelle nötig
pytest tests/ -m "not network" --cov=application --cov-report=term-missing  # dieselbe Suite mit Coverage (Floor: 62%, siehe [tool.coverage.report])
```

---

## Entwicklerwerkzeuge

### Screenshot-Galerie-Generator

`tools/regenerate_screenshots.py` regeneriert die Offscreen-Visual-Verifikationsgalerie für UI-Review: die Hauptfensterseiten (Home, Einstellungen, Über) × Sprachen × dunkle/helle Designs, plus Burn-in-Dialog, Fortschrittsmodals, thematisierter Dateidialog (dunkel/hell) und Meldungsbox pro Sprache.

```bash
QT_QPA_PLATFORM=offscreen python tools/regenerate_screenshots.py [--out DIR] [--langs en,es,...]
```

- Ausgabe standardmäßig nach `/tmp/srt4u-shots` (46 PNGs mit den 6 UI-Sprachen); vorherige PNGs im Zielverzeichnis werden überschrieben.
- Die Qt-Offscreen-Plattform wird ohne Display genutzt, und der FFmpeg-Burn-in-Worker ist neutralisiert, sodass das Tool headless sicher läuft.
- Die resultierende Größe und deklarierte Mindestgröße jedes Dialogs werden als schneller Geometrie-Sanity-Check gedruckt (`size == min` erwartet).
- Das Tool ist via `tests/test_screenshot_tool.py`-Smoke-Test gegen Bit-Rot geschützt, der es in einem Subprozess bei jedem CI-Testjob ausführt.

---

## Logs & Fehlerbehebung

Fehler werden in eine rotierende Logdatei geschrieben (512 KB × 3), statt verschluckt zu werden:

| Plattform | Ort |
|---|---|
| Windows | `%APPDATA%\SRT4U\srt4u.log` |
| macOS | `~/Library/Application Support/SRT4U/srt4u.log` |
| Linux | `~/.config/SRT4U/srt4u.log` (oder `$XDG_CONFIG_HOME/SRT4U/srt4u.log`) |

Sie zeichnet Konfigurations-Lese-/Schreibfehler, Übersetzungsengine-Fehler pro Block, FFmpeg-Erkennungs-/Dauer-/Dimensionsprobleme, unerwartete Ausnahmen (mit Traceback) und den finalen Exit-Code auf. Qts eigene Meldungen werden dorthin geroutet (`qWarning`/`qCritical`/`qFatal`, und `qDebug`/`qInfo` auf Debug-Level), sodass Multimedia-/Codec-Warnungen und Plattform-Plugin-Diagnostik neben den app-eigenen Einträgen auftauchen. Wenn ein Fehler anwendersichtbar ist — Einstellungen nicht gespeichert, unvollständige Übersetzung, unlesbare Einstellungsdatei, unbehandelter Fehler — zeigt die App einen Dialog mit Verweis auf diese Datei.

---

## Unterstützte Formate

| Format | Erweiterung | Lesen | Schreiben | Stilerhalt |
|---|---|:---:|:---:|:---:|
| SubRip Subtitle | `.srt` | Ja | Ja | Ja (HTML-Tags) |
| Web Video Text Tracks | `.vtt` | Ja | Ja | Ja (Cue-Settings & Tags) |
| Advanced SubStation Alpha | `.ass` / `.ssa` | Ja | Ja | Ja (Stile & Positionen) |
| Klartext-Dialog | `.txt` | Ja | Ja | Nur Zeilen |
