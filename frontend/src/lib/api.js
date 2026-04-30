import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 60000 });

export const health = () => api.get("/health").then((r) => r.data);

export const uploadFile = (file, onProgress) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
        .post("/jobs/upload", fd, {
            headers: { "Content-Type": "multipart/form-data" },
            onUploadProgress: (p) => {
                if (onProgress && p.total) onProgress(p.loaded / p.total);
            },
        })
        .then((r) => r.data);
};

export const listJobs = () => api.get("/jobs").then((r) => r.data.jobs);
export const getJob = (id) => api.get(`/jobs/${id}`).then((r) => r.data);
export const deleteJob = (id) => api.delete(`/jobs/${id}`).then((r) => r.data);
export const reprocessJob = (id) => api.post(`/jobs/${id}/reprocess`).then((r) => r.data);
export const pagePreviewUrl = (id, page) => `${API}/jobs/${id}/preview/${page}`;
export const dxfUrl = (id) => `${API}/jobs/${id}/dxf`;

export const correctEntity = (jobId, payload) => api.post(`/jobs/${jobId}/correct`, payload).then((r) => r.data);
export const addEntity = (jobId, payload) => api.post(`/jobs/${jobId}/entities`, payload).then((r) => r.data);
export const updateEntity = (id, payload) => api.patch(`/entities/${id}`, payload).then((r) => r.data);

export const listRules = () => api.get("/rules").then((r) => r.data.rules);
export const updateRule = (id, payload) => api.patch(`/rules/${id}`, payload).then((r) => r.data);
export const deleteRule = (id) => api.delete(`/rules/${id}`).then((r) => r.data);
