# CAD Assist — Desktop Build

This folder turns the web app into a **native desktop binary** for Windows, macOS or Linux.
The resulting executable bundles:

- a compiled FastAPI backend (PyInstaller → single file),
- the React production build,
- Electron (thin shell that spawns the backend and loads the UI).

No Python, Node or Tesseract needs to be installed by end users — except Tesseract on Windows, which is bundled separately into `bin/` (see below).

---

## Build on your target OS

> You must build on the OS you want to ship for. Electron does not cross-compile reliably across platforms.

### Prerequisites

- Node.js 18+ and `yarn`
- Python 3.10+ with `pip`
- PyInstaller: `pip install pyinstaller`

### Windows (PowerShell)

```powershell
cd desktop
npm install

# 1. Build backend (produces bin\cadassist-backend.exe)
python -m pip install -r ..\backend\requirements.txt pyinstaller
cd ..\backend
pyinstaller --noconfirm --onefile --name cadassist-backend `
            --add-data "processing;processing" `
            --add-data "learning;learning" `
            --add-data "storage;storage" `
            server.py
mkdir -Force ..\desktop\bin
copy dist\cadassist-backend.exe ..\desktop\bin\
cd ..\desktop

# 2. Copy Tesseract (required for OCR). Download the installer from
#    https://github.com/UB-Mannheim/tesseract/wiki, then copy the binary:
copy "C:\Program Files\Tesseract-OCR\tesseract.exe" bin\
xcopy /E /Y "C:\Program Files\Tesseract-OCR\tessdata" bin\tessdata\

# 3. Build React frontend
cd ..\frontend
yarn install
yarn build
xcopy /E /Y build ..\desktop\frontend-build\
cd ..\desktop

# 4. Package the installer (NSIS .exe)
npx electron-builder --win --x64
# Output: desktop\dist\CAD Assist Setup 1.0.0.exe
```

### macOS

```bash
cd desktop
npm install
python3 -m pip install -r ../backend/requirements.txt pyinstaller
(cd ../backend && pyinstaller --noconfirm --onefile --name cadassist-backend \
    --add-data "processing:processing" --add-data "learning:learning" \
    --add-data "storage:storage" server.py)
mkdir -p bin && cp ../backend/dist/cadassist-backend bin/
cp "$(which tesseract)" bin/ 2>/dev/null || true
(cd ../frontend && yarn install && yarn build)
rm -rf frontend-build && cp -R ../frontend/build frontend-build
npx electron-builder --mac
# Output: desktop/dist/CAD Assist-1.0.0.dmg
```

### Linux

```bash
cd desktop
npm install
python3 -m pip install -r ../backend/requirements.txt pyinstaller
(cd ../backend && pyinstaller --noconfirm --onefile --name cadassist-backend \
    --add-data "processing:processing" --add-data "learning:learning" \
    --add-data "storage:storage" server.py)
mkdir -p bin && cp ../backend/dist/cadassist-backend bin/
(cd ../frontend && yarn install && yarn build)
rm -rf frontend-build && cp -R ../frontend/build frontend-build
npx electron-builder --linux AppImage deb
# Output: desktop/dist/CAD Assist-1.0.0.AppImage
```

---

## How the runtime works

On launch, `main.js`:

1. Resolves `bin/cadassist-backend[.exe]` (shipped in `resources/bin`).
2. Spawns it as a child process bound to `127.0.0.1:58001`, passing `CADASSIST_DATA` = the platform-standard userData folder so SQLite, uploads, previews and DXF outputs live there.
3. Waits up to 20 s for `/api/health` to return 200.
4. Opens a `BrowserWindow` loading `frontend-build/index.html`.

The backend process is killed on quit. There is no public-facing server.

---

## Icons

Put platform icons in `icons/`:

- `icons/icon.ico` (Windows, multi-res)
- `icons/icon.icns` (macOS)
- `icons/icon.png` (Linux, 512×512)

See `electron-builder` docs for formats.
