import type { ProcessingJob } from "../types";

const API_BASE_URL = "http://localhost:8000";

async function readJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string" ? payload.detail : fallbackMessage;
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export async function fetchJobs(): Promise<ProcessingJob[]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs`);
  return readJson<ProcessingJob[]>(response, "Failed to load jobs");
}

export async function fetchJob(jobId: string): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);
  return readJson<ProcessingJob>(response, "Failed to load job");
}

export async function uploadVideo(file: File): Promise<ProcessingJob> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/jobs/upload`, {
    method: "POST",
    body: formData,
  });

  return readJson<ProcessingJob>(response, "Failed to upload video");
}

export async function updatePage(
  jobId: string,
  pageId: string,
  payload: { rotation?: number; deleted?: boolean },
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/pages/${pageId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return readJson<ProcessingJob>(response, "Failed to update page");
}

export async function reorderPages(
  jobId: string,
  orderedPageIds: string[],
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/pages/reorder`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ orderedPageIds }),
  });

  return readJson<ProcessingJob>(response, "Failed to reorder pages");
}

export async function startExport(jobId: string): Promise<ProcessingJob["export"]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/export`, {
    method: "POST",
  });

  return readJson<ProcessingJob["export"]>(response, "Failed to start export");
}
