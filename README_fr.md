<div align="center">
  <img src="assets/icon.png" alt="logo SRT4U" height="96" />
</div>

# SRT4U - Subtitle Processor

[![License: GPL-3.0-only](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

[**English**](README.md) | [**Español**](README_es.md) | [**Deutsch**](README_de.md) | **Français** | [**Italiano**](README_it.md) | [**中文**](README_zh.md)

Application desktop pour traduire, éditer, nettoyer et convertir les fichiers de sous-titres (`.srt`, `.vtt`, `.ass`/`.ssa`, `.txt`) avec un lecteur vidéo synchronisé en temps réel et un export direct de burn-in vidéo.

Release stable actuelle : **[v1.4.10](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.10)**. Voir [RELEASE_NOTES.md](RELEASE_NOTES.md) pour les détails.

![Aperçu SRT4U](assets/preview_en.png)

---

## Fonctionnalités

- **Interface multilingue (i18n)** :
  - Détection automatique de la langue du système au démarrage via `QLocale`.
  - Changement de langue en direct sans redémarrer l'app.
  - 7 langues prises en charge : anglais (`en`), espagnol (`es`), portugais (`pt`), allemand (`de`), italien (`it`), français (`fr`) et chinois simplifié (`zh-CN`).
  - Double accès : sélecteur rapide dans la barre supérieure et sélection persistante dans les Paramètres.
- **Burn-In vidéo (export hardsub)** :
  - Incruste durablement les sous-titres dans les fichiers vidéo (`.mp4`, `.mkv`, `.webm`, etc.).
  - Personnalisation visuelle : taille de police, couleur (blanc, jaune, cyan) et boîtes de lecture (semi-transparentes, pleines ou contour).
  - Rendu à résolution adaptative : les sous-titres sont mis à l'échelle proportionnellement à la hauteur vidéo (de 480p à 4K et Reels/TikTok verticaux).
  - Nettoyeur anti-chevauchement automatique : empêche les timecodes de sous-titres qui se chevauchent de se percuter à l'écran.
  - Modale de progression temps réel avec vitesse d'encodage (x), temps écoulé et ETA.
- **Studio de traduction interactif** :
  - Éditeur de cartes côte à côte en direct pour relire et affiner les traductions ligne par ligne.
  - Synchronisé avec le lecteur vidéo intégré (cliquez un sous-titre pour aller à cette image vidéo).
  - Recherche et filtrage instantanés des cues.
- **Moteurs de traduction** :
  - Google Translate : niveau gratuit intégré sans configuration ni clés API.
  - DeepL : prise en charge des clés API Free et Pro.
  - OpenAI / LLM locaux : compatible avec les endpoints OpenAI, Ollama et OpenRouter.
- **Nettoyeur automatisé** : supprime les canaux Telegram (`t.me`), URLs, crédits fansub, pubs et marqueurs musicaux (`♪`) tout en préservant dialogues valides et tags de formatage (`<i>`, `<b>`, styles ASS).
- **Convertisseur de formats** : conversion bidirectionnelle entre `.srt`, `.vtt`, `.ass` et texte brut `.txt`.
- **Traitement par lots** : file d'attente multifichier avec suivi de progression par fichier.
- **Analytique sous-titres & QA déterministe** : métriques groupées contenu/timing/qualité plus validation par règles (`analyze`/`qa`, JSON/CSV).
- **Benchmarks de traduction** : comparaison reproductible de fournisseurs avec rapports JSON/CSV et carnet d'analyse hors ligne.
- **Historique SQLite local** : chaque exécution enregistrée avec métriques agrégées (page Historique, CLI `history`) ; ni textes, ni clés, ni médias stockés.
- **API REST locale** (extra optionnel `[api]`) : `/api/v1` avec jobs d'analyse, QA, traduction/traitement/transcription/pipeline, historique, benchmarks, docs OpenAPI — se lie à localhost par défaut, sans authentification.
- **Transcription Whisper locale** (extra optionnel `[transcription]`) : audio/vidéo → sous-titres alimentant analytique, QA, nettoyage, traduction, burn-in. Modèles non embarqués ; téléchargés à la première utilisation.
- **Pipeline média de bout en bout** : `srt4u pipeline` / page Pipeline / `POST /api/v1/pipeline` chaînant transcription → nettoyage → analytique → QA → traduction optionnelle → QA final → export → burn-in optionnel, avec erreurs par étape et annulation coopérative (best-effort) : les jobs en file sont abandonnés, ceux en cours finissent et leur résultat est écarté.
- **CLI headless** : traite des lots, analyse les métriques de sous-titres et exécute un QA déterministe avec exports JSON/CSV sans démarrer PyQt6.
- **Exécution parallèle** : traduction par blocs multithread pour accélérer les gros fichiers de sous-titres.
- **Thème Glass sombre / clair** : UI Glassmorphism moderne avec bascule de thème instantanée.

---

## Installation & Exécution

### Prérequis
- Python 3.10 ou supérieur
- `pip`

### Exécuter depuis les sources

```bash
# Cloner le dépôt
git clone https://github.com/marodriguezd/SRT4U-Subtitle-Processor.git
cd SRT4U-Subtitle-Processor

# Créer et activer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Sous Windows : .venv\Scripts\activate

# Installer les dépendances (chemin checkout source : même stack de base que `pip install .`)
pip install -r requirements.txt

# Lancer l'application desktop
python main.py

# Traiter sans ouvrir l'UI
python -m application.cli process input.srt --output output.srt --clean
```

### Extras optionnels

```bash
pip install ".[api]"            # API REST locale : srt4u serve (/api/v1, OpenAPI ; localhost par défaut, sans auth)
pip install ".[transcription]"  # Whisper local : srt4u transcribe / pipeline media
pip install ".[dev]"            # pytest + ruff pour contributeurs
```

> [!NOTE]
> L'installation de base (`pip install .`) inclut la stack GUI et CLI (PyQt6 +
> `deep-translator`) ainsi qu'analytique, QA, traduction, historique et
> pipeline pour les entrées de sous-titres. `requirements.txt` reflète ces exigences
> de base pour les checkouts source et la CI. Les extras `[api]`, `[transcription]` et
> `[dev]` ajoutent FastAPI, `faster-whisper` et les outils de développement. Les modèles
> Whisper ne sont pas embarqués ; ils se téléchargent à la première utilisation avec avis
> préalable (`SRT4U_WHISPER_MODEL_DIR` déplace le cache). Le burn-in requiert FFmpeg ; les builds
> CI embarquent un exécutable FFmpeg, tandis que les installs source ont besoin d'un FFmpeg
> utilisable sur `PATH` ou dans le bundle applicatif.

### Démarrage en 60 secondes

```bash
python -m application.cli analyze input.srt --json
python -m application.cli qa input.srt --strict
python -m application.cli process input.srt --clean --translate --target en
python -m application.cli transcribe clip.mp4 --model small --language auto
python -m application.cli pipeline clip.mp4 --translate --target en -o out.srt --stats-json
python -m application.cli serve  # docs sur http://127.0.0.1:8000/docs
```

Architecture (GUI/CLI/API → services → fournisseurs/SQLite/FFmpeg) et guides
par domaine : [docs/cli.md](docs/cli.md), [docs/api.md](docs/api.md),
[docs/transcription.md](docs/transcription.md), [docs/pipeline.md](docs/pipeline.md),
[docs/database.md](docs/database.md), [docs/tech-debt.md](docs/tech-debt.md).

### Binaires précompilés

La release stable actuelle est **[v1.4.10](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.10)** (pas une prérelease). GitHub Actions compile et joint ces assets pour chaque tag stable `v*` :

| Asset | Plateforme | Architecture |
|---|---|---|
| [`SRT4U-Windows-x64.exe`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Windows-x64.exe) | Windows 10/11 | x86_64 |
| [`SRT4U-Linux-x86_64.AppImage`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Linux-x86_64.AppImage) | Linux | x86_64 |
| [`SRT4U-Linux-x86_64.tar.gz`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-Linux-x86_64.tar.gz) | Linux | x86_64 |
| [`SRT4U-macOS.dmg`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/SRT4U-macOS.dmg) | macOS (Apple Silicon) | **arm64 uniquement** — ne se lancera pas sur Mac Intel |
| [`checksums.txt`](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/download/v1.4.10/checksums.txt) | Checksums SHA-256 des assets ci-dessus | — |

Les builds CI embarquent un exécutable FFmpeg statique épinglé en version, donc le burn-in
fonctionne out of the box ; les exigences de bibliothèques runtime de la plateforme s'appliquent
toujours. Les installs source (section précédente) ont besoin d'un FFmpeg utilisable sur `PATH`
pour le burn-in.

---

## CLI headless

La CLI réutilise `SubtitleService` pour nettoyer, traduire, convertir les formats et traiter les répertoires par lots sans créer d'application Qt. Après installation du paquet, lancez `srt4u process` ; depuis un checkout utilisez `python -m application.cli process`. Les presets JSON et options comme `--translate --source auto --target es --engine ollama` sont pris en charge. Voir [docs/cli.md](docs/cli.md) pour exemples, clés de presets et comportement de sortie.

## Analytique & QA

`analyze` calcule des métriques groupées de contenu, timing, qualité et traitement. `qa` rapporte des problèmes de sous-titres déterministes avec seuils configurables. Les deux commandes supportent JSON ; l'analytique peut aussi être exportée en CSV. Voir [docs/analytics.md](docs/analytics.md) pour définitions des métriques, défauts de règles et exemples d'export CLI.

## Fournisseurs de traduction & métriques

`TranslationService` dispatche via `ProviderRegistry` vers `Google`, `DeepL` ou l'endpoint compatible OpenAI (les alias `openai`, `llm` et `ollama` partagent l'implémentation ; le fournisseur demandé est préservé dans les métriques). Les erreurs sont normalisées (`error_type`), les retries sont opt-in et les fallbacks explicites, configurables et sans cycle. `translate_with_metrics()` retourne `TranslationResult` avec `TranslationMetrics` sérialisable en JSON ; la CLI les affiche avec `--stats` ou `--stats-json`, et `estimated_cost` reste `null` — aucun tarif inventé.

`benchmark` fait tourner un jeu de données versionné contre plusieurs fournisseurs sur N runs et exporte JSON/CSV pour analyse hors ligne (`notebooks/benchmark_analysis.ipynb` + `analysis/benchmark_analysis.py`). Les exécutions sont enregistrées dans un historique SQLite local (CLI `history`, page Historique, `--store` pour les benchmarks) : métriques agrégées uniquement — ni textes, ni clés, ni médias jamais stockés.

Approfondissements : [docs/providers.md](docs/providers.md), [docs/benchmarking.md](docs/benchmarking.md), [docs/benchmark_analysis.md](docs/benchmark_analysis.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/transcription.md](docs/transcription.md) et [docs/pipeline.md](docs/pipeline.md).

## Exécuter les tests

La suite de tests couvre parsing, nettoyage, conversion inter-formats, traduction libre, flux UI, régression de layout UI (détection de texte rogné en 6 langues × 2 thèmes) et invariants de géométrie des dialogues :

```bash
pytest tests/ -m "not network"  # pas de réseau, clés ou modèles Whisper nécessaires
pytest tests/ -m "not network" --cov=application --cov-report=term-missing  # même suite avec couverture (plancher : 62 %, voir [tool.coverage.report])
```

---

## Outils développeur

### Générateur de galerie de captures

`tools/regenerate_screenshots.py` régénère la galerie de vérification visuelle offscreen utilisée pendant la revue UI : les pages de la fenêtre principale (Accueil, Paramètres, À propos) × langues × thèmes sombre/clair, plus le dialogue de burn-in, les modales de progression, le dialogue de fichier thémé (sombre/clair) et la boîte de message par langue.

```bash
QT_QPA_PLATFORM=offscreen python tools/regenerate_screenshots.py [--out DIR] [--langs en,es,...]
```

- Sortie par défaut vers `/tmp/srt4u-shots` (46 PNG avec les 6 langues UI) ; les PNG précédents du répertoire cible sont écrasés.
- La plateforme offscreen Qt est utilisée sans affichage, et le worker FFmpeg de burn-in est neutralisé, donc l'outil tourne headless en sécurité.
- La taille résultante et la taille minimale déclarée de chaque dialogue sont affichées comme contrôle rapide de géométrie (`size == min` attendu).
- L'outil est protégé contre le bit-rot par le smoke test `tests/test_screenshot_tool.py`, qui l'exécute en sous-processus à chaque job de test CI.

---

## Logs & Dépannage

Les échecs sont écrits dans un fichier de log rotatif (512 Ko × 3) au lieu d'être avalés :

| Plateforme | Emplacement |
|---|---|
| Windows | `%APPDATA%\SRT4U\srt4u.log` |
| macOS | `~/Library/Application Support/SRT4U/srt4u.log` |
| Linux | `~/.config/SRT4U/srt4u.log` (ou `$XDG_CONFIG_HOME/SRT4U/srt4u.log`) |

Il enregistre les échecs de lecture/écriture de configuration, les erreurs de moteur de traduction par bloc, les problèmes de détection/durée/dimensions FFmpeg, les exceptions inattendues (avec traceback) et le code de sortie final. Les messages propres de Qt y sont routés aussi (`qWarning`/`qCritical`/`qFatal`, et `qDebug`/`qInfo` au niveau debug), donc avertissements multimédia/codec et diagnostics de plugin de plateforme apparaissent aux côtés des entrées propres de l'app. Quand un échec est visible pour l'utilisateur — paramètres non sauvegardés, traduction incomplète, fichier de paramètres illisible, erreur non gérée — l'app montre un dialogue pointant vers ce fichier.

---

## Formats pris en charge

| Format | Extension | Lecture | Écriture | Préservation du style |
|---|---|:---:|:---:|:---:|
| SubRip Subtitle | `.srt` | Oui | Oui | Oui (tags HTML) |
| Web Video Text Tracks | `.vtt` | Oui | Oui | Oui (cue settings & tags) |
| Advanced SubStation Alpha | `.ass` / `.ssa` | Oui | Oui | Oui (styles & positions) |
| Dialogue texte brut | `.txt` | Oui | Oui | Lignes uniquement |
