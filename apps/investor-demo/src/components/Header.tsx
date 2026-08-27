import { FlaskConical } from "lucide-react";

const links = [
  ["Overview", "overview"],
  ["Live demo", "live-demo"],
  ["Architecture", "architecture"],
  ["Validation", "validation"],
  ["Roadmap", "roadmap"],
] as const;

interface HeaderProps {
  onRun: () => void;
}

export function Header({ onRun }: HeaderProps) {
  return (
    <header className="site-header">
      <a className="brand" href="#overview" aria-label="VLEP home">
        VLEP
      </a>
      <nav aria-label="Primary navigation">
        {links.map(([label, id]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>
      <button className="button button-primary header-action" type="button" onClick={onRun}>
        <FlaskConical size={17} aria-hidden="true" />
        Run synthetic demo
      </button>
    </header>
  );
}
