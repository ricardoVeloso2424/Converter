# Converter

Desktop image/video converter with a simple Tkinter GUI, built in Python and powered by FFmpeg.

Supports resize with aspect-ratio control, quality presets, live progress bar with ETA and cancel button.  
Works on macOS and Windows (Python app) and can be bundled as a standalone `.app` / `.exe` with PyInstaller.

---

## Features

- Convert **images** and **videos**:
  - Images: `png, jpg, jpeg, webp, bmp, tif, tiff, gif`
  - Videos: `mp4, webm, avi, mov, mkv`
- Resize with:
  - Custom width/height
  - Aspect ratios: `Original, 16:9, 4:3, 1:1, 9:16, 3:2, 4:5`
- Option to **keep original resolution**
- Video quality presets:
  - `Alta`, `Normal`, `Rápido` (different CRF / presets / bitrates)
- Uses hardware encoders when available:
  - `h264_videotoolbox` (macOS), `h264_nvenc`, `h264_qsv`, `h264_amf` (Windows/Linux)
- For videos:
  - Progress bar with percentage
  - ETA (HH:MM:SS)
  - Cancel button (terminates FFmpeg process)
- For images:
  - Proper EXIF rotation
  - Letterbox/pillarbox for “Original” aspect ratio
  - JPEG output with quality 90 / optimize

---

## Requirements

### Common

- FFmpeg (`ffmpeg` + `ffprobe`) available either:
  - In the system `PATH`, or
  - In a local `ffmpeg-bin/` folder next to the script/binary.

The script automatically searches in:

- The script directory
- `ffmpeg-bin/`
- `imageio_ffmpeg` path
- System `PATH`

If it doesn’t find FFmpeg/ffprobe, it exits with a clear error message.

---

## macOS

### 1. Install system dependencies

```bash
brew install ffmpeg
```

### 2. Create and activate virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install pillow imageio-ffmpeg
```

### 4. Run

```bash
python converter.py
```

---

## Windows

### 1. Create and activate virtualenv

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Python dependencies

```powershell
pip install pillow imageio-ffmpeg
```

### 3. FFmpeg

- Put `ffmpeg.exe` + `ffprobe.exe` in `.fmpeg-bin\` OR install FFmpeg in PATH.

### 4. Run

```powershell
python converter.py
```

---

## Usage

1. Escolher ficheiro.
2. Definir formato, ratio, resolução, qualidade.
3. (Opcional) Manter resolução original.
4. Guardar como…
5. Converter (progresso com ETA para vídeos).
6. Cancelar disponível durante conversão de vídeo.

---

## Building a standalone app

### macOS – `.app`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pillow imageio-ffmpeg pyinstaller
brew install ffmpeg
pyinstaller --windowed --name Converter converter.py
```

Result: `dist/Converter.app`

#### Bundling FFmpeg

```bash
cd dist/Converter.app/Contents/MacOS
mkdir ffmpeg-bin
cp /usr/local/bin/ffmpeg ffmpeg-bin/
cp /usr/local/bin/ffprobe ffmpeg-bin/
```

### Windows – `.exe`

```powershell
pyinstaller --windowed --name Converter converter.py
```

Result: `dist/Converter.exe`

---

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pillow imageio-ffmpeg
python converter.py
```

