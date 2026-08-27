import { ArrowRight, Check, Circle, FlaskConical, Landmark, PackageOpen } from "lucide-react";

const horizons = [
  ["Now · Investor MVP", PackageOpen, ["Public synthetic demo", "Transparent repository", "CI workflow definitions", "Architecture + validation docs"]],
  ["Next · Research Beta", FlaskConical, ["Formal mapping registry", "Simulation harness", "Reviewer workflow", "De-identified integration sandbox"]],
  ["Later · Clinical Research", Landmark, ["Institutional partners", "Gold-standard labels", "Prospective validation", "Regulatory strategy"]],
] as const;

interface RoadmapProps {
  onRun: () => void;
}

export function Roadmap({ onRun }: RoadmapProps) {
  return (
    <section className="roadmap-section section-shell" id="roadmap">
      <div className="section-heading">
        <h2>A credible path from research artifact to governed platform.</h2>
      </div>
      <div className="roadmap-grid">
        {horizons.map(([title, Icon, items], index) => (
          <div className={index === 2 ? "future" : ""} key={title}>
            <Icon size={27} aria-hidden="true" />
            <h3>{title}</h3>
            <ul>
              {items.map((item) => <li key={item}>{index === 2 ? <Circle /> : <Check />} {item}</li>)}
            </ul>
          </div>
        ))}
      </div>
      <div className="final-cta">
        <h3>Inspect the working system</h3>
        <button className="button button-primary" type="button" onClick={onRun}>Run synthetic demo <ArrowRight size={17} /></button>
        <a className="button button-secondary" href="https://github.com/mmanthe37/vlep-csep-investor-demo" target="_blank" rel="noreferrer">View source on GitHub</a>
      </div>
    </section>
  );
}
