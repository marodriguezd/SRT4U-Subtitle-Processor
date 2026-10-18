<div align="center">
  <img src="assets/icon.png" alt="logo SRT4U" height="96" />
</div>

# SRT4U - Subtitle Processor

[![License: GPL-3.0-only](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

[**English**](README.md) | [**Español**](README_es.md) | [**Deutsch**](README_de.md) | [**Français**](README_fr.md) | **Italiano** | [**中文**](README_zh.md)

App desktop per tradurre, modificare, pulire e convertire file di sottotitoli (`.srt`, `.vtt`, `.ass`/`.ssa`, `.txt`) con un video player sincronizzato in tempo reale ed export diretto di burn-in video.

Release stabile corrente: **[v1.0.0](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.0.0)**. Vedi [RELEASE_NOTES.md](RELEASE_NOTES.md) per i dettagli.

![Anteprima SRT4U](assets/preview_en.png)

---

## Funzionalità

- **Interfaccia multilingua (i18n)**:
  - Rilevamento automatico della lingua di sistema all'avvio via `QLocale`.
  - Cambio lingua live senza riavviare l'app.
  - 7 lingue supportate: inglese (`en`), spagnolo (`es`), portoghese (`pt`), tedesco (`de`), italiano (`it`), francese (`fr`) e cinese semplificato (`zh-CN`).
  - Doppio accesso: selettore rapido nella barra superiore e selezione persistente nelle Impostazioni.
- **Burn-In video (export hardsub)**:
  - Incorpora permanentemente i sottotitoli nei file video (`.mp4`, `.mkv`, `.webm`, ecc.).
  - Personalizzazione visiva: dimensione font, colore (bianco, giallo, ciano) e box di lettura (semitrasparenti, pieni o contorno).
  - Rendering a risoluzione adattiva: i sottotitoli scalano proporzionalmente all'altezza video (da 480p a 4K e Reels/TikTok verticali).
  - Sanitizer anti-sovrapposizione automatico: impedisce ai timecode sovrapposti di collidere sullo schermo.
  - Modale di avanzamento in tempo reale con velocità di codifica (x), tempo trascorso ed ETA.
- **Studio di traduzione interattivo**:
  - Editor live di card fianco a fianco per rivedere e rifinire le traduzioni riga per riga.
  - Sincronizzato col video player integrato (clicca un sottotitolo per andare a quel frame video).
  - Ricerca e filtro istantanei dei cue.
- **Motori di traduzione**:
  - Google Translate: livello gratuito integrato senza setup o API key.
  - DeepL: supporto chiavi API Free e Pro.
  - OpenAI / LLM locali: compatibile con endpoint OpenAI, Ollama e OpenRouter.
- **Pulitore automatizzato**: rimuove canali Telegram (`t.me`), URL, crediti fansub, annunci e marcatori musicali (`♪`) preservando dialoghi validi e tag di formattazione (`<i>`, `<b>`, stili ASS).
- **Convertitore di formati**: conversione bidirezionale tra `.srt`, `.vtt`, `.ass` e testo puro `.txt`.
- **Elaborazione batch**: coda multifile con tracciamento avanzamento per file.
- **Analitica sottotitoli & QA deterministico**: metriche raggruppate contenuto/timing/qualità più validazione a regole (`analyze`/`qa`, JSON/CSV).
- **Benchmark di traduzione**: confronto riproducibile tra provider con report JSON/CSV e notebook di analisi offline.
- **Cronologia SQLite locale**: ogni esecuzione registrata con metriche aggregate (pagina Cronologia, CLI `history`); mai testi, chiavi o media archiviati.
- **API REST locale** (extra opzionale `[api]`): `/api/v1` con job di analisi, QA, traduzione/elaborazione/trascrizione/pipeline, cronologia, benchmark, docs OpenAPI — bind su localhost di default, nessuna autenticazione.
- **Trascrizione Whisper locale** (extra opzionale `[transcription]`): audio/video → sottotitoli che alimentano analitica, QA, pulizia, traduzione, burn-in. Modelli non inclusi; scaricati al primo uso.
- **Pipeline media end-to-end**: `srt4u pipeline` / pagina Pipeline / `POST /api/v1/pipeline` che concatena trascrizione → pulizia → analitica → QA → traduzione opzionale → QA finale → export → burn-in opzionale, con errori per fase e cancellazione cooperativa (best-effort): i job in coda sono scartati, quelli in corso finiscono e il loro risultato è scartato.
- **CLI headless**: elabora batch, analizza metriche dei sottotitoli ed esegue QA deterministico con export JSON/CSV senza avviare PyQt6.
- **Esecuzione parallela**: traduzione a blocchi multithread per velocizzare file di sottotitoli grandi.
- **Tema Glass scuro / chiaro**: UI Glassmorphism moderna con cambio tema istantaneo.

---

## Installazione & Esecuzione

### Requisiti
- Python 3.10 o superiore
- `pip`

### Esecuzione dai sorgenti

```bash
# Clonare il repository
git clone https://github.com/marodriguezd/SRT4U-Subtitle-Processor.git
cd SRT4U-Subtitle-Processor

# Creare e attivare l'ambiente virtuale
python -m venv .venv
source .venv/bin/activate  # Su Windows: .venv\Scripts\activate

# Installare le dipendenze (percorso checkout sorgenti: stesso stack base di `pip install .`)
pip install -r requirements.txt

# Avviare l'applicazione desktop
python main.py

# Elaborare senza aprire la UI
python -m application.cli process input.srt --output output.srt --clean
```

### Extra opzionali

```bash
pip install ".[api]"            # API REST locale: srt4u serve (/api/v1, OpenAPI; localhost di default, nessuna auth)
pip install ".[transcription]"  # Whisper locale: srt4u transcribe / pipeline media
pip install ".[dev]"            # pytest + ruff per contributori
```

> [!NOTE]
> L'installazione base (`pip install .`) include lo stack GUI e CLI (PyQt6 +
> `deep-translator`) oltre ad analitica, QA, traduzione, cronologia e
> pipeline per input di sottotitoli. `requirements.txt` rispecchia questi requisiti
> base per checkout sorgenti e CI. Gli extra `[api]`, `[transcription]` e
> `[dev]` aggiungono FastAPI, `faster-whisper` e strumenti di sviluppo. I modelli
> Whisper non sono inclusi; si scaricano al primo uso con preavviso
> (`SRT4U_WHISPER_MODEL_DIR` sposta la cache). Il burn-in richiede FFmpeg; le build
> CI includono un eseguibile FFmpeg, mentre le installazioni da sorgenti necessitano di un FFmpeg
> usabile su `PATH` o nel bundle applicativo.

### Avvio in 60 secondi

```bash
python -m application.cli analyze input.srt --json
python -m application.cli qa input.srt --strict
python -m application.cli process input.srt --clean --translate --target en
python -m application.cli transcribe clip.mp4 --model small --language auto
python -m application.cli pipeline clip.mp4 --translate --target en -o out.srt --stats-json
python -m application.cli serve  # docs su http://127.0.0.1:8000/docs
```

Architettura (GUI/CLI/API → servizi → provider/SQLite/FFmpeg) e guide
per area: [docs/cli.md](docs/cli.md), [docs/api.md](docs/api.md),
[docs/transcription.md](docs/transcription.md), [docs/pipeline.md](docs/pipeline.md),
[docs/database.md](docs/database.md), [docs/tech-debt.md](docs/tech-debt.md).

### Binari precompilati

La release stabile corrente è **[v1.0.0](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.0.0)** (non una prerelease). GitHub Actions compila e allega questi asset per ogni tag stabile `v*`:

| Asset | Piattaforma | Architettura |
|---|---|---|
| [`SRT4U-Windows-x64.exe`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.0.0/SRT4U-Windows-x64.exe) | Windows 10/11 | x86_64 |
| [`SRT4U-Linux-x86_64.AppImage`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.0.0/SRT4U-Linux-x86_64.AppImage) | Linux | x86_64 |
| [`SRT4U-Linux-x86_64.tar.gz`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.0.0/SRT4U-Linux-x86_64.tar.gz) | Linux | x86_64 |
| [`SRT4U-macOS.dmg`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.0.0/SRT4U-macOS.dmg) | macOS (Apple Silicon) | **solo arm64** — non si avvia su Mac Intel |
| [`checksums.txt`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.0.0/checksums.txt) | Checksum SHA-256 degli asset sopra | — |

Le build CI includono un eseguibile FFmpeg statico pinnato in versione, quindi il burn-in
funziona out of the box; restano validi i requisiti di librerie runtime della piattaforma.
Le installazioni da sorgenti (sezione precedente) necessitano di un FFmpeg usabile su `PATH`
per il burn-in.

---

## CLI headless

La CLI riusa `SubtitleService` per pulire, tradurre, convertire formati ed elaborare directory in batch senza creare un'applicazione Qt. Dopo aver installato il pacchetto, esegui `srt4u process`; da un checkout usa `python -m application.cli process`. Preset JSON e opzioni come `--translate --source auto --target es --engine ollama` sono supportati. Vedi [docs/cli.md](docs/cli.md) per esempi, chiavi dei preset e comportamento di output.

## Analitica & QA

`analyze` calcola metriche raggruppate di contenuto, timing, qualità ed elaborazione. `qa` riporta problemi deterministici dei sottotitoli con soglie configurabili. Entrambi i comandi supportano JSON; l'analitica può anche essere esportata in CSV. Vedi [docs/analytics.md](docs/analytics.md) per definizioni delle metriche, default delle regole ed esempi di export CLI.

## Provider di traduzione & metriche

`TranslationService` smista tramite `ProviderRegistry` a `Google`, `DeepL` o l'endpoint compatibile OpenAI (gli alias `openai`, `llm` e `ollama` condividono l'implementazione; il provider richiesto è preservato nelle metriche). Gli errori sono normalizzati (`error_type`), i retry sono opt-in e i fallback espliciti, configurabili e senza cicli. `translate_with_metrics()` restituisce `TranslationResult` con `TranslationMetrics` serializzabile in JSON; la CLI li stampa con `--stats` o `--stats-json`, ed `estimated_cost` resta `null` — nessuna tariffa inventata.

`benchmark` esegue un dataset versionato contro diversi provider su N run ed esporta JSON/CSV per analisi offline (`notebooks/benchmark_analysis.ipynb` + `analysis/benchmark_analysis.py`). Le esecuzioni sono registrate in una cronologia SQLite locale (CLI `history`, pagina Cronologia, `--store` per i benchmark): solo metriche aggregate — mai testi, chiavi o media archiviati.

Approfondimenti: [docs/providers.md](docs/providers.md), [docs/benchmarking.md](docs/benchmarking.md), [docs/benchmark_analysis.md](docs/benchmark_analysis.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/transcription.md](docs/transcription.md) e [docs/pipeline.md](docs/pipeline.md).

## Esecuzione dei test

La suite di test copre parsing, pulizia, conversione tra formati, traduzione libera, flussi UI, regressione layout UI (rilevamento testo troncato in 7 lingue × 2 temi) e invarianti di geometria dei dialoghi:

```bash
pytest tests/ -m "not network"  # nessuna rete, chiavi o modelli Whisper necessari
pytest tests/ -m "not network" --cov=application --cov-report=term-missing  # stessa suite con copertura (floor: 62%, vedi [tool.coverage.report])
```

La suite predefinita è deterministica: nessuna rete, chiavi API, modelli Whisper o media. Le suite di integrazione opt-in (traduzione Google gratuita, Whisper reale, e2e con media reali) e le loro variabili d'ambiente esatte sono documentate in [docs/testing.md](docs/testing.md).

---

## Strumenti sviluppatore

### Generatore galleria screenshot

`tools/regenerate_screenshots.py` rigenera la galleria di verifica visiva offscreen usata durante la review UI: le pagine della finestra principale (Home, Impostazioni, Info) × le 7 lingue UI × temi scuro/chiaro, più il dialogo di burn-in, i modali di avanzamento, il dialogo file temizzato (scuro/chiaro) e il message box per lingua.

```bash
QT_QPA_PLATFORM=offscreen python tools/regenerate_screenshots.py [--out DIR] [--langs en,es,...]
```

- Output di default in `/tmp/srt4u-shots` (74 PNG con le 7 lingue UI); i PNG precedenti nella directory target sono sovrascritti.
- La piattaforma offscreen Qt è usata senza display, e il worker FFmpeg di burn-in è neutralizzato, quindi lo strumento gira headless in sicurezza.
- La dimensione risultante e minima dichiarata di ogni dialogo sono stampate come rapido sanity check di geometria (`size == min` atteso).
- Lo strumento è protetto dal bit-rot dallo smoke test `tests/test_screenshot_tool.py`, che lo esegue in un sottoprocesso a ogni job di test CI.

---

## Log & Risoluzione problemi

I fallimenti sono scritti in un file di log rotante (512 KB × 3) invece di essere inghiottiti:

| Piattaforma | Posizione |
|---|---|
| Windows | `%APPDATA%\SRT4U\srt4u.log` |
| macOS | `~/Library/Application Support/SRT4U/srt4u.log` |
| Linux | `~/.config/SRT4U/srt4u.log` (o `$XDG_CONFIG_HOME/SRT4U/srt4u.log`) |

Registra fallimenti di lettura/scrittura configurazione, errori del motore di traduzione per blocco, problemi di rilevamento/durata/dimensioni FFmpeg, eccezioni inattese (con traceback) e l'exit code finale. Anche i messaggi propri di Qt vi sono instradati (`qWarning`/`qCritical`/`qFatal`, e `qDebug`/`qInfo` a livello debug), così avvisi multimedia/codec e diagnostica dei plugin di piattaforma appaiono accanto alle voci proprie dell'app. Quando un fallimento è visibile all'utente — impostazioni non salvate, traduzione incompleta, file impostazioni illeggibile, errore non gestito — l'app mostra un dialogo che punta a questo file.

---

## Formati supportati

| Formato | Estensione | Lettura | Scrittura | Preservazione stile |
|---|---|:---:|:---:|:---:|
| SubRip Subtitle | `.srt` | Sì | Sì | Sì (tag HTML) |
| Web Video Text Tracks | `.vtt` | Sì | Sì | Sì (cue settings & tag) |
| Advanced SubStation Alpha | `.ass` / `.ssa` | Sì | Sì | Sì (stili & posizioni) |
| Dialogo testo puro | `.txt` | Sì | Sì | Solo righe |
