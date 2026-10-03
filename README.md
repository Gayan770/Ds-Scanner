# AIA - Embedded PDF Extractor (Desktop Application)

This repository contains a high-performance, completely offline, Windows standalone executable bridging a Python backend with a HTML/JS/CSS frontend via **PyWebView**. 

## Setup and Architecture

- **Backend**: `main.py`
  - Utilizes `pywebview` to render the frontend via Windows' native EdgeChromium (WebView2) for maximum rendering performance and hardware acceleration.
  - Minimal imports at boot sequence ensures a near-instant cold-start.
- **Frontend**: `index.html` (along with CSS/JS assets)
  - Talks natively to the Python backend via PyWebView's JS Bridge `window.pywebview.api`.
  - Zero external dependencies. Everything runs offline in an air-gapped environment.

## The Standalone Executable

The production-ready standalone executable is located in the **`dist`** directory:
**`dist/AIA_PDF_Extractor.exe`**

It is a completely standalone `.exe` (approximately 12MB). The target machine does *not* need Python installed, and it operates entirely offline without external data dependencies.

## Rebuilding the Application

If you make modifications to `main.py`, `index.html`, or the assets, you can rebuild the `.exe` yourself. 

### Prerequisites

Ensure you have a Python environment set up. We recommend creating a virtual environment:

```powershell
# 1. Create and activate virtual environment (Windows Powershell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
```

### Build Command

We have included an automated build script `build.py` that handles the PyInstaller configuration. It packages the application into a single executable, injects the necessary app icons, and ensures zero-console-window behavior.

```powershell
python build.py
```

The resulting executable will be placed at `dist/AIA_PDF_Extractor.exe`.

## Technical Optimizations applied

- **Native EdgeChromium Engine**: Provides fluid CSS transitions and leverages GPU rendering, ensuring enterprise UI responsiveness.
- **Lazy Loading Strategy**: Heavy imports (`olefile`, `zipfile`, `io`, etc.) are deferred and only loaded lazily during active processing, bypassing startup bottlenecks.
- **Parallel Threading**: The backend extraction logic is offloaded onto an asynchronous background thread. This keeps the PyWebView main UI event loop unlocked and buttery-smooth.
- **Direct IPC Bridge**: Eliminates the need for local Flask/FastAPI servers or web sockets, heavily reducing latency and memory footprint.

<video src="demo/demo.mp4" controls width="100%"></video>
