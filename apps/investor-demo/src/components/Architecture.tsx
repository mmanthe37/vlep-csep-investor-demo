import { Check, Database, FileInput, GitCompareArrows, ListChecks, ScanSearch, ShieldCheck } from "lucide-react";

const stages = [
  ["Ingest", "Synthetic FHIR-like events and structured fixtures", FileInput, "Events & fixtures"],
  ["Normalize", "Canonical concepts and source preservation", ScanSearch, "Canonical evidence"],
  ["Ledger", "Append-only SHA-256 hash chain", Database, "Evidence ledger"],
  ["Assert", "Evidence-linked phenotype assertions", ListChecks, "Assertions"],
  ["Model", "Deterministic research scoring with uncertainty", GitCompareArrows, "Scoring engine"],
  ["Resolve", "CSEP snapshot and framework reinterpretation", ShieldCheck, "Framework snapshot"],
] as const;

export function Architecture() {
  return (
    <section className="architecture-section section-shell" id="architecture">
      <div className="section-heading">
        <h2>One deterministic core. Six inspectable stages.</h2>
        <p>The research MVP separates immutable evidence from versioned interpretation, so every output can be reproduced and audited.</p>
      </div>
      <ol className="architecture-rail">
        {stages.map(([name, description, Icon, output], index) => (
          <li key={name}>
            <span className="architecture-number">{index + 1}</span>
            <strong>{name}</strong>
            <span>{description}</span>
            <div className="architecture-output"><Icon size={20} /> {output}</div>
          </li>
        ))}
      </ol>
      <div className="contract-grid">
        <div>
          <h3>Formal contract</h3>
          <code>P<sub>snapshot</sub>(t) = F(L<sub>≤t</sub>, N)</code>
        </div>
        <div>
          <h3>System invariants</h3>
          <ul>
            <li><Check /> Original evidence is never rewritten</li>
            <li><Check /> Same ledger + framework = same snapshot</li>
            <li><Check /> Conditional mappings require human review</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
