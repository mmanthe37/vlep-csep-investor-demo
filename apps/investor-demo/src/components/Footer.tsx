import type { DemoBundle } from "../types";

export function Footer({ bundle }: { bundle: DemoBundle }) {
  return (
    <footer className="site-footer section-shell">
      <div>
        <strong>VLEP Research MVP</strong>
        <span>Synthetic data only · Not for clinical use</span>
      </div>
      <nav aria-label="Documentation links">
        <a href="./docs/RESEARCH_DISCLAIMER.md">Research disclaimer</a>
        <a href="./docs/MODEL_CARD.md">Model card</a>
        <a href="./docs/DATA_CARD.md">Data card</a>
        <a href="./SECURITY.md">Security</a>
      </nav>
      <div className="source-links">
        {bundle.sources.map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>{source.title}</a>)}
      </div>
      <code>Bundle {bundle.bundle_hash.slice(0, 16)}…</code>
    </footer>
  );
}
