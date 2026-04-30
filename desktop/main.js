// CAD Assist — Electron main process.
// Spawns the bundled Python/PyInstaller backend binary and loads the React build.
// No visible server. Backend is owned by this process and killed on quit.

const { app, BrowserWindow, Menu, shell, dialog } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const http = require("http");

let backendProcess = null;
let mainWindow = null;

const BACKEND_PORT = 58001; // non-standard to avoid collisions
const BACKEND_HOST = "127.0.0.1";
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;

function log(...a) { console.log("[cadassist]", ...a); }

function resolveBackendBinary() {
    const exe = process.platform === "win32" ? "cadassist-backend.exe" : "cadassist-backend";
    const candidates = [
        path.join(process.resourcesPath || __dirname, "bin", exe),
        path.join(__dirname, "bin", exe),
        path.join(__dirname, "..", "bin", exe),
    ];
    for (const c of candidates) { if (fs.existsSync(c)) return c; }
    return null;
}

function startBackend() {
    const bin = resolveBackendBinary();
    if (!bin) {
        dialog.showErrorBox("Backend missing",
            "Could not find the cadassist-backend binary. Build it first:\n\n" +
            "  cd backend && pyinstaller ...  (see desktop/README.md)");
        app.exit(1);
        return;
    }
    log("starting backend", bin);
    const env = { ...process.env, HOST: BACKEND_HOST, PORT: String(BACKEND_PORT), CADASSIST_DATA: path.join(app.getPath("userData"), "data") };
    backendProcess = spawn(bin, ["--host", BACKEND_HOST, "--port", String(BACKEND_PORT)], { env, stdio: ["ignore", "pipe", "pipe"] });
    backendProcess.stdout.on("data", (d) => log("backend:", d.toString().trim()));
    backendProcess.stderr.on("data", (d) => log("backend-err:", d.toString().trim()));
    backendProcess.on("exit", (code) => {
        log("backend exited", code);
        backendProcess = null;
        if (code !== 0 && !app.isQuitting) {
            dialog.showErrorBox("Backend stopped", `The backend exited unexpectedly with code ${code}. The app will close.`);
            app.quit();
        }
    });
}

function waitForBackend(timeoutMs = 20000) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
        const tick = () => {
            const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
                if (res.statusCode === 200) resolve();
                else retry();
            });
            req.on("error", retry);
            req.setTimeout(1000, () => { req.destroy(); retry(); });
        };
        const retry = () => {
            if (Date.now() - start > timeoutMs) reject(new Error("backend health timeout"));
            else setTimeout(tick, 400);
        };
        tick();
    });
}

async function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1440,
        height: 900,
        minWidth: 1100,
        minHeight: 700,
        backgroundColor: "#07090c",
        title: "CAD Assist",
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
            preload: path.join(__dirname, "preload.js"),
        },
    });

    // Inject backend URL so the React app knows where to call
    mainWindow.webContents.on("did-finish-load", () => {
        mainWindow.webContents.executeJavaScript(
            `window.__BACKEND_URL__ = ${JSON.stringify(BACKEND_URL)};`
        ).catch(() => {});
    });

    // External links open in system browser
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: "deny" };
    });

    const frontendPath = path.join(__dirname, "frontend-build", "index.html");
    if (fs.existsSync(frontendPath)) {
        await mainWindow.loadFile(frontendPath, { query: { backend: BACKEND_URL } });
    } else {
        await mainWindow.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(
            `<html><body style="background:#07090c;color:#e6ebf2;font-family:system-ui;padding:40px">
             <h2>Frontend build missing</h2>
             <p>Run <code>yarn --cwd ../frontend build</code> first (or use the provided build script).</p>
             </body></html>`
        ));
    }

    Menu.setApplicationMenu(null);
}

app.whenReady().then(async () => {
    startBackend();
    try {
        await waitForBackend();
    } catch (e) {
        dialog.showErrorBox("Backend did not start", String(e));
    }
    await createWindow();
});

app.on("window-all-closed", () => {
    app.isQuitting = true;
    if (backendProcess) { try { backendProcess.kill(); } catch (_) {} }
    if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
    app.isQuitting = true;
    if (backendProcess) { try { backendProcess.kill(); } catch (_) {} }
});
