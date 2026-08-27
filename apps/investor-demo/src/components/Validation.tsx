import { Check, X } from "lucide-react";

const maturity = [
  ["Implemented now", ["Deterministic synthetic pipeline", "Chain verification", "Snapshot hashing", "Version diff", "Unit tests + production build"]],
  ["Next evidence", ["Property-based invariants", "Simulation stress tests", "Calibration analysis", "External expert review"]],
  ["Clinical threshold", ["Retrospective cohort validation", "Prospective protocol", "Security/compliance review", "Regulatory determination"]],
] as const;

export function Validation() {
  return (
    <section className="validation-section section-shell" id="validation">
      <div className="section-heading">
        <h2>Validation is a program, not a badge.</h2>
        <p>Software correctness is necessary, but it is not the same thing as clinical validity or clinical utility.</p>
      </div>
      <div className="maturity-ladder">
        {maturity.map(([title, items], index) => (
          <div key={title}>
            <h3><span>{index + 1}</span>{title}</h3>
            <ul>{items.map((item) => <li key={item}><Check /> {item}</li>)}</ul>
          </div>
        ))}
      </div>
      <div className="claim-boundary">No clinical performance claims are made in this prototype.</div>
      <div className="proves-grid">
        <div>
          <h3>What the demo proves</h3>
          <ul>
            <li><Check /> Software traceability</li>
            <li><Check /> Deterministic execution</li>
            <li><Check /> Auditable mappings</li>
          </ul>
        </div>
        <div>
          <h3>What it does not prove</h3>
          <ul className="does-not">
            <li><X /> Diagnostic validity</li>
            <li><X /> Clinical utility</li>
            <li><X /> Patient safety</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
