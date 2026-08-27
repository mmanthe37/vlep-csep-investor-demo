import { ArrowRight, Check, ShieldCheck } from "lucide-react";

interface HeroProps {
  onRun: () => void;
}

const stages = ["Ingest", "Normalize", "Ledger", "Assert", "Model", "Resolve"];

export function Hero({ onRun }: HeroProps) {
  return (
    <section className="hero section-shell" id="overview">
      <div className="hero-copy">
        <h1>A living phenotype, recomputed as medical language evolves.</h1>
        <p className="hero-lede">
          VLEP preserves source evidence, resolves a six-dimensional current-state epilepsy profile,
          and reinterprets that profile under versioned classification frameworks.
        </p>
        <div className="hero-actions">
          <button className="button button-primary" type="button" onClick={onRun}>
            Run synthetic demo <ArrowRight size={18} aria-hidden="true" />
          </button>
          <a className="button button-secondary" href="#architecture">
            Explore the architecture
          </a>
        </div>
        <p className="safety-line">
          <ShieldCheck size={17} aria-hidden="true" />
          Research prototype · Synthetic data only · Not for clinical use
        </p>
      </div>

      <div className="formal-system" aria-label="VLEP formal system overview">
        <div className="formal-title">
          <strong>VLEP</strong>
          <span>=</span>
          <code>(L, N, F, P<sub>snapshot</sub>)</code>
        </div>
        <div className="formal-grid">
          <ol className="stage-list">
            {stages.map((stage, index) => (
              <li key={stage}>
                <span>{index + 1}</span>
                <div>
                  <strong>{stage}</strong>
                  <small>{stageDescriptions[index]}</small>
                </div>
              </li>
            ))}
          </ol>
          <div className="profile-code">
            <div className="code-heading">Current profile</div>
            <pre>{`{
  "seizure": "versioned term",
  "etiology": "ranked evidence",
  "syndrome": "reviewable",
  "biomarkers": ["EEG", "MRI"],
  "comorbidity": "reported",
  "treatment": "observed trial"
}`}</pre>
            <div className="integrity-row">
              <Check size={16} aria-hidden="true" />
              <span>Snapshot integrity</span>
              <code>sha256: verified</code>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

const stageDescriptions = [
  "Acquire source observations",
  "Map canonical concepts",
  "Chain immutable evidence",
  "Link evidence to assertions",
  "Score with uncertainty",
  "Build versioned CSEP",
];
