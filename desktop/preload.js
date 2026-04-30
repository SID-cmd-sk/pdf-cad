// Minimal preload. Exposes backend URL to the renderer.
const { contextBridge } = require("electron");
contextBridge.exposeInMainWorld("cadassist", {
    backendUrl: () => window.__BACKEND_URL__ || "http://127.0.0.1:58001",
});
