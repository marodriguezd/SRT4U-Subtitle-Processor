# SRT4U - Subtitle Processor (PyQt Version)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.8%2B-yellow?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt](https://img.shields.io/badge/PyQt-6.4%2B-3D9D5B)](https://pypi.org/project/PyQt6/)

---

## Translate, Clean, and Convert SRT/VTT Subtitles  

![Application Screenshot](https://raw.githubusercontent.com/marodriguezd/SRT4U_Subtitle-Processor/main/assets/demo-screenshot.png)

A native desktop application built with PyQt6 for processing subtitle files with translation and cleaning capabilities. Features a modern dark theme interface with intuitive controls.

## Features  

- **Robust SRT/VTT Support**:  
   - Import and process SRT or VTT files, even with common formatting errors.
   - The app automatically handles non-standard files, correcting issues like missing index numbers or incorrect timestamp separators.
   - Export processed subtitles in your chosen format (SRT or VTT).  

- **Smart Translation System**:  
   - Translate subtitles into dozens of languages while preserving the original timing structure.
   - Optimized translation calls ensure maximum reliability and timing integrity for each subtitle block.
   - Auto-detection of the source language for optimal translation quality.

- **Advanced Subtitle Cleaning**:  
   - Automatically removes spam content, promotional messages, and unwanted text.
   - Filters out Telegram links, promotional URLs, and subtitle credits.
   - Cleans musical notes and formatting tags that interfere with readability.

- **Native Desktop Experience**:  
   - Built with PyQt6 for native look and feel across all platforms.
   - Modern dark theme interface with intuitive controls.
   - Native file dialogs for seamless file and directory selection.  
   - Real-time progress tracking with detailed status messages.
   - Responsive threading to keep the UI smooth during processing.

- **Output Format Flexibility**:  
   - Choose between SRT or VTT output format regardless of the input format.
   - Automatic format conversion with proper headers (WEBVTT for VTT files).
   - Preserves timing precision and ensures correct subtitle numbering.  

---

## Important Notes  

### Format Tolerance
SRT4U is designed to be highly tolerant of common subtitle file issues. It can automatically parse and correct:
- Files with **missing subtitle index numbers**.
- Files using non-standard timestamp separators (e.g., `00:00:00 - 00:01:00` instead of `00:00:00,000 --> 00:01:00,000`).
- Inconsistent line endings or extra blank lines.

### About VTT File Processing  
Internally, SRT4U processes subtitle files in a standardized SRT-like format. If you import a VTT file with additional features such as styles, positioning, or other metadata, these will be **stripped out during processing** to ensure compatibility.  
- The application ensures that text content and timing are perfectly preserved.  
- However, **styles or metadata specific to VTT will not be retained** when exporting back to VTT.  

---

## How to Use  

### Quick Start Guide

1. **Launch the Application**
   ```bash
   python main.py
   ```

2. **Select Your Subtitle File**
   - Click "Select SRT/VTT file" button
   - Choose your subtitle file from the native file dialog
   - Supported formats: `.srt`, `.vtt`

3. **Choose Output Location**  
   - Click "Select output directory" button
   - Pick where you want the processed file to be saved

4. **Configure Translation (Optional)**
   - Check "Enable translation" if you want to translate subtitles
   - Enter a target language code (e.g., `es` for Spanish, `en` for English, `fr` for French).

5. **Select Output Format**
   - Choose between `srt` or `vtt` format from the dropdown menu.

6. **Start Processing**  
   - Click the "Process" button to begin.
   - Monitor progress through the progress bar and status messages.

7. **Results**
   - A success notification will appear when processing completes.
   - The processed file will be saved with a `_processed` suffix in your chosen directory.
   - Any errors will be displayed with detailed messages.

### Language Codes Reference
Common language codes for translation:
- `en` - English
- `es` - Spanish  
- `fr` - French
- `de` - German
- `it` - Italian
- `pt` - Portuguese
- `ru` - Russian
- `ja` - Japanese
- `ko` - Korean
- `zh` - Chinese (Simplified)
- `ar` - Arabic
- `hi` - Hindi  

---

## Installation & Requirements

### System Requirements
- **Python 3.8 or later**
- **Windows, macOS, or Linux**
- **Internet connection** (required for the translation feature)

### Dependencies Installation

Install required libraries using pip:

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install PyQt6>=6.4.0 deep-translator>=1.11.4
```

### Quick Installation

1. **Clone the repository**:  
   ```bash  
   git clone https://github.com/marodriguezd/SRT4U_Subtitle-Processor.git
   cd SRT4U_Subtitle-Processor  
   ```  

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:  
   ```bash  
   python main.py  
   ```  

---

## Troubleshooting

### Common Issues

**"No module named 'PyQt6'" Error**
```bash
pip install PyQt6>=6.4.0
```

**Translation Not Working**  
- Check your internet connection.
- Verify the language code is correct (e.g., `es`, not `spanish`). The translation service may have temporarily blocked your IP due to high request volume.

**Input File Issues**
- **SRT4U is designed to handle most format errors automatically.** If a file still fails, it may be severely corrupted. Ensure it contains recognizable timestamp lines.
- Check file encoding (UTF-8 is recommended).

**UI Not Responding**
- Large files may take a moment to process.
- Check the progress bar for updates. Translation of very long subtitles can take several minutes.

### Performance Tips

- **For large files**: Processing may take 1-3 minutes depending on file size and whether translation is enabled.
- **Translation speed**: Depends on the number of subtitle blocks and internet connection stability.
- **Memory usage**: Minimal, even with large subtitle files.

---

## Changelog from NiceGUI Version

### ✅ Improvements
- **Native Desktop Experience**: True desktop app with OS-native dialogs.
- **Better Performance**: No web server overhead or browser dependency.
- **Robust Parsing Engine**: Intelligently handles common format errors like missing index numbers and non-standard timestamp separators.
- **Enhanced Threading**: Responsive UI during processing with PyQt signals.
- **Modern Interface**: Dark theme with improved contrast and readability.
- **Superior Error Handling**: Clear, specific error messages and user feedback.

### 🔄 Maintained Features
- All original subtitle processing logic.
- Optimized translation calls to preserve timing integrity.
- Spam cleaning with the same pattern recognition.
- Support for both SRT and VTT formats.
- Progress tracking and status updates.