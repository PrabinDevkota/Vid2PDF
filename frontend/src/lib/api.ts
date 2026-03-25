import type { ProcessingJob } from "../types";

const API_BASE_URL = "http://localhost:8000";

export async function fetchJobs(): Promise<ProcessingJob[]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs`);
  if (!response.ok) {
    throw new Error("Failed to load jobs");
  }

  return response.json();
}

export async function uploadVideo(file: File): Promise<ProcessingJob> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/jobs/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("Failed to upload video");
  }

  return response.json();
}
