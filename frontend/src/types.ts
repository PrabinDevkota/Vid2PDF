export type JobStatus = "queued" | "processing" | "ready" | "failed";

export interface PagePreview {
  id: string;
  pageNumber: number;
  previewLabel: string;
  previewUrl: string | null;
  sharpnessScore: number;
  segmentStart: number;
  segmentEnd: number;
  rotation: number;
}

export interface ProcessingStage {
  key: string;
  label: string;
  state: "pending" | "complete";
}

export interface ProcessingJob {
  id: string;
  filename: string;
  status: JobStatus;
  createdAt: string;
  notes: string[];
  stages: ProcessingStage[];
  pages: PagePreview[];
}
