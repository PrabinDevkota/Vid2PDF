import type { PageEdits, ProcessingJob, ProcessingMode, Sensitivity } from "../types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
const ARTIFACT_BASE_URL = `${API_BASE_URL}/artifacts`;

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

export interface TrimRange {
  trimStart?: number | null;
  trimEnd?: number | null;
}

export async function uploadVideo(
  file: File,
  processingMode: ProcessingMode,
  ocrLanguage = "eng",
  trim: TrimRange = {},
): Promise<ProcessingJob> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("processing_mode", processingMode);
  formData.append("ocr_language", ocrLanguage);
  if (trim.trimStart != null) {
    formData.append("trim_start", String(trim.trimStart));
  }
  if (trim.trimEnd != null) {
    formData.append("trim_end", String(trim.trimEnd));
  }

  const response = await fetch(`${API_BASE_URL}/api/jobs/upload`, {
    method: "POST",
    body: formData,
  });

  return readJson<ProcessingJob>(response, "Failed to upload video");
}

export async function createJobFromUrl(
  url: string,
  processingMode: ProcessingMode,
  ocrLanguage = "eng",
  trim: TrimRange = {},
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/from-url`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      url,
      processingMode,
      ocrLanguage,
      trimStart: trim.trimStart ?? null,
      trimEnd: trim.trimEnd ?? null,
    }),
  });

  return readJson<ProcessingJob>(response, "Failed to import video from URL");
}

export async function fetchOcrLanguages(): Promise<{ languages: string[]; default: string }> {
  const response = await fetch(`${API_BASE_URL}/api/ocr/languages`);
  return readJson(response, "Failed to load OCR languages");
}

export async function reprocessJob(
  jobId: string,
  sensitivity: Sensitivity,
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/reprocess`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sensitivity }),
  });

  return readJson<ProcessingJob>(response, "Failed to re-process session");
}

export async function updatePage(
  jobId: string,
  pageId: string,
  payload: { rotation?: number; deleted?: boolean; edits?: PageEdits },
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

export async function bulkUpdatePages(
  jobId: string,
  payload: { pageIds: string[]; rotation?: number; deleted?: boolean },
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/pages`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return readJson<ProcessingJob>(response, "Failed to update selected pages");
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

export async function addManualPage(
  jobId: string,
  timestampSeconds: number,
): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/pages/manual`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ timestampSeconds }),
  });

  return readJson<ProcessingJob>(response, "Failed to add page from video");
}

export async function restoreRejectedFrame(
  jobId: string,
  rejectedId: string,
): Promise<ProcessingJob> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/rejected/${rejectedId}/restore`,
    { method: "POST" },
  );

  return readJson<ProcessingJob>(response, "Failed to restore the rejected page");
}

export async function cancelJob(jobId: string): Promise<ProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/cancel`, {
    method: "POST",
  });

  return readJson<ProcessingJob>(response, "Failed to cancel processing");
}

export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string" ? payload.detail : "Failed to delete session";
    throw new Error(detail);
  }
}

export async function startExport(jobId: string): Promise<ProcessingJob["export"]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/export`, {
    method: "POST",
  });

  return readJson<ProcessingJob["export"]>(response, "Failed to start export");
}

export async function startTextExport(jobId: string): Promise<ProcessingJob["textExport"]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/export/text`, {
    method: "POST",
  });

  return readJson<ProcessingJob["textExport"]>(response, "Failed to start text export");
}

export async function startSearchableExport(
  jobId: string,
): Promise<ProcessingJob["searchableExport"]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/export/searchable`, {
    method: "POST",
  });

  return readJson<ProcessingJob["searchableExport"]>(
    response,
    "Failed to start searchable export",
  );
}

export function subscribeToJobEvents(
  onJob: (job: ProcessingJob) => void,
  onHealthChange?: (healthy: boolean) => void,
): () => void {
  const source = new EventSource(`${API_BASE_URL}/api/events`);
  source.onopen = () => onHealthChange?.(true);
  source.onerror = () => onHealthChange?.(false);
  source.onmessage = (event) => {
    try {
      onJob(JSON.parse(event.data) as ProcessingJob);
    } catch {
      // Malformed event; the polling fallback keeps state fresh.
    }
  };
  return () => source.close();
}

export function resolveArtifactUrl(url: string | null): string | null {
  if (!url) {
    return null;
  }

  if (url.startsWith("data:") || url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }

  if (url.startsWith("/artifacts/")) {
    return `${ARTIFACT_BASE_URL}${url.replace("/artifacts", "")}`;
  }

  if (url.startsWith("artifacts/")) {
    return `${API_BASE_URL}/${url}`;
  }

  return url;
}
