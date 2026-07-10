import { Check, Circle, Loader2 } from "lucide-react";
import type { ProcessingJob } from "../types";

type WorkflowStep = "upload" | "process" | "review" | "export";

interface StepDef {
  key: WorkflowStep;
  label: string;
}

const STEPS: StepDef[] = [
  { key: "upload", label: "Upload" },
  { key: "process", label: "Process" },
  { key: "review", label: "Review" },
  { key: "export", label: "Export" },
];

function getActiveStep(job: ProcessingJob): WorkflowStep {
  if (
    job.export.status === "ready" ||
    job.export.status === "processing" ||
    job.textExport?.status === "ready" ||
    job.textExport?.status === "processing"
  ) {
    return "export";
  }
  if (job.status === "ready") {
    return "review";
  }
  if (job.status === "queued" || job.status === "processing") {
    return "process";
  }
  return "upload";
}

function getStepState(
  step: WorkflowStep,
  activeStep: WorkflowStep,
  job: ProcessingJob,
): "complete" | "active" | "pending" {
  const order: WorkflowStep[] = ["upload", "process", "review", "export"];
  const stepIndex = order.indexOf(step);
  const activeIndex = order.indexOf(activeStep);

  if (stepIndex < activeIndex) {
    return "complete";
  }
    if (stepIndex === activeIndex) {
      if (step === "process" && job.status === "failed") {
        return "active";
      }
      if (
        step === "export" &&
        (job.export.status === "failed" || job.textExport?.status === "failed")
      ) {
        return "active";
      }
      return "active";
    }
  return "pending";
}

interface WorkflowStepperProps {
  job: ProcessingJob;
}

export function WorkflowStepper({ job }: WorkflowStepperProps) {
  const activeStep = getActiveStep(job);

  return (
    <div className="workflow-stepper">
      {STEPS.map((step, index) => {
        const state = getStepState(step.key, activeStep, job);
        return (
          <div className="workflow-stepper__item" key={step.key}>
            <div className={`workflow-stepper__step workflow-stepper__step--${state}`}>
              <span className="workflow-stepper__marker">
                {state === "complete" ? (
                  <Check size={14} />
                ) : state === "active" &&
                  (job.status === "processing" ||
                    job.status === "queued" ||
                    job.export.status === "processing" ||
                    job.textExport?.status === "processing") ? (
                  <Loader2 size={14} className="spin" />
                ) : (
                  <Circle size={10} />
                )}
              </span>
              <span className="workflow-stepper__label">{step.label}</span>
            </div>
            {index < STEPS.length - 1 ? (
              <div
                className={`workflow-stepper__connector ${
                  state === "complete" ? "workflow-stepper__connector--complete" : ""
                }`}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
