import type { PropsWithChildren } from "react";

interface SectionCardProps extends PropsWithChildren {
  title: string;
  eyebrow?: string;
}

export function SectionCard({ title, eyebrow, children }: SectionCardProps) {
  return (
    <section className="section-card">
      {eyebrow ? <p className="section-eyebrow">{eyebrow}</p> : null}
      <h2>{title}</h2>
      <div className="section-body">{children}</div>
    </section>
  );
}
