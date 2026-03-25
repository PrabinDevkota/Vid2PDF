import { useEffect, useState } from "react";
import type { PagePreview, ProcessingJob } from "../../types";
import { SectionCard } from "../../components/SectionCard";

interface PageReviewBoardProps {
  job: ProcessingJob | null;
}

function moveItem(items: PagePreview[], fromIndex: number, toIndex: number) {
  const nextItems = [...items];
  const [moved] = nextItems.splice(fromIndex, 1);
  nextItems.splice(toIndex, 0, moved);
  return nextItems;
}

export function PageReviewBoard({ job }: PageReviewBoardProps) {
  const [pages, setPages] = useState<PagePreview[]>([]);

  useEffect(() => {
    setPages(job?.pages ?? []);
  }, [job]);

  function rotatePage(pageId: string) {
    setPages((currentPages) =>
      currentPages.map((page) =>
        page.id === pageId
          ? { ...page, rotation: (page.rotation + 90) % 360 }
          : page,
      ),
    );
  }

  function deletePage(pageId: string) {
    setPages((currentPages) => currentPages.filter((page) => page.id !== pageId));
  }

  function shiftPage(pageId: string, direction: -1 | 1) {
    setPages((currentPages) => {
      const index = currentPages.findIndex((page) => page.id === pageId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= currentPages.length) {
        return currentPages;
      }

      return moveItem(currentPages, index, nextIndex);
    });
  }

  return (
    <SectionCard eyebrow="Review" title="Page review board">
      {!job ? (
        <p className="muted">Select a job to review extracted pages.</p>
      ) : (
        <div className="review-board">
          <div className="review-summary">
            <h3>{job.filename}</h3>
            <p className="muted">
              Review pages before export. Current page actions only update local
              UI state and are ready to be wired to backend persistence.
            </p>
            <ul className="stage-list">
              {job.stages.map((stage) => (
                <li key={stage.key}>
                  <span>{stage.label}</span>
                  <strong>{stage.state}</strong>
                </li>
              ))}
            </ul>
          </div>
          <div className="page-grid">
            {pages.map((page, index) => (
              <article className="page-card" key={page.id}>
                <div className="page-card__preview">
                  <div
                    className="page-placeholder"
                    style={{ transform: `rotate(${page.rotation}deg)` }}
                  >
                    <span>{page.previewLabel}</span>
                  </div>
                </div>
                <div className="page-card__content">
                  <h4>Page {index + 1}</h4>
                  <p className="muted">
                    Segment {page.segmentStart.toFixed(1)}s to{" "}
                    {page.segmentEnd.toFixed(1)}s
                  </p>
                  <p className="muted">
                    Sharpness score: {page.sharpnessScore.toFixed(2)}
                  </p>
                </div>
                <div className="page-card__actions">
                  <button onClick={() => shiftPage(page.id, -1)} type="button">
                    Move up
                  </button>
                  <button onClick={() => shiftPage(page.id, 1)} type="button">
                    Move down
                  </button>
                  <button onClick={() => rotatePage(page.id)} type="button">
                    Rotate
                  </button>
                  <button onClick={() => deletePage(page.id)} type="button">
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
