import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  timeout: 30_000,
});

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/api/upload", formData);
  return response.data;
}
