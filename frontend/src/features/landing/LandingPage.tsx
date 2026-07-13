import { Link } from "react-router-dom";
import {
  ArrowRight,
  Copy,
  ExternalLink,
  FileText,
  Lock,
  PenLine,
  ScanText,
  Video,
} from "lucide-react";

const FEATURES = [
  {
    Icon: Copy,
    title: "Unique page detection",
    body: "Stable-segment analysis and perceptual dedup pick one clean frame per page — no near-duplicate spam in your PDF.",
  },
  {
    Icon: ScanText,
    title: "Searchable text PDF",
    body: "Tesseract OCR reads every page and Tectonic typesets the text into a clean, justified LaTeX document.",
  },
  {
    Icon: FileText,
    title: "LaTeX source included",
    body: "Download the generated .tex alongside the PDF and restyle the document however you like.",
  },
  {
    Icon: PenLine,
    title: "Page editor",
    body: "Crop, rotate, draw, add text, and blur sensitive regions before exporting. Edits re-render server-side.",
  },
  {
    Icon: Video,
    title: "Frame recovery",
    body: "Missed a page? Scrub the source video and save any frame as an extra page in one click.",
  },
  {
    Icon: Lock,
    title: "Local & private",
    body: "Everything runs on your machine. Videos and documents never leave your computer.",
  },
];

const STEPS = [
  {
    title: "Upload a recording",
    body: "Screen recordings of digital documents, or handheld videos of physical pages.",
  },
  {
    title: "Review the pages",
    body: "The pipeline extracts one sharp frame per page. Reorder, edit, or recover frames as needed.",
  },
  {
    title: "Export two PDFs",
    body: "A pixel-faithful image PDF, and a searchable text PDF typeset with LaTeX.",
  },
];

export function LandingPage() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="landing-nav__inner">
          <div className="landing-brand">
            <span className="landing-brand__mark" aria-hidden="true">
              V
            </span>
            Vid2PDF
          </div>
          <nav className="landing-nav__links">
            <a
              className="landing-nav__link"
              href="https://github.com/PrabinDevkota"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
              <ExternalLink size={13} aria-hidden="true" />
            </a>
            <Link className="primary-button" to="/app">
              Open app
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <span className="landing-pill">Free · Open source · Runs locally</span>
          <h1>
            Turn document videos into
            <br />
            clean, searchable PDFs.
          </h1>
          <p>
            Vid2PDF watches a screen recording of a document being read, finds each
            unique page, and rebuilds it as a polished PDF — with OCR text and LaTeX
            typesetting included.
          </p>
          <div className="landing-hero__actions">
            <Link className="primary-button primary-button--large" to="/app">
              Open Vid2PDF
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <a
              className="secondary-button primary-button--large"
              href="https://github.com/PrabinDevkota"
              target="_blank"
              rel="noreferrer"
            >
              View on GitHub
            </a>
          </div>

          <div className="landing-mock" aria-hidden="true">
            <div className="landing-mock__chrome">
              <span />
              <span />
              <span />
            </div>
            <div className="landing-mock__strip">
              <div className="landing-mock__film">
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
              <ArrowRight className="landing-mock__arrow" size={18} />
              <div className="landing-mock__pages">
                <div className="landing-mock__page" />
                <div className="landing-mock__page" />
                <div className="landing-mock__page" />
              </div>
            </div>
            <div className="landing-mock__caption">
              46 frames sampled → 3 unique pages → 2 PDFs
            </div>
          </div>
        </section>

        <section className="landing-section">
          <h2>How it works</h2>
          <div className="landing-steps">
            {STEPS.map((step, index) => (
              <div className="landing-step" key={step.title}>
                <span className="landing-step__number">{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="landing-section">
          <h2>Built for real documents</h2>
          <div className="landing-features">
            {FEATURES.map(({ Icon, title, body }) => (
              <div className="landing-feature" key={title}>
                <Icon size={18} aria-hidden="true" />
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="landing-cta">
          <h2>Reconstruct your first document</h2>
          <p>No account, no upload limits, no cloud. Just a video in and PDFs out.</p>
          <Link className="primary-button primary-button--large" to="/app">
            Open Vid2PDF
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>MIT licensed · Built with FastAPI, OpenCV, Tesseract, and Tectonic</span>
        <a href="https://github.com/PrabinDevkota" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </footer>
    </div>
  );
}
