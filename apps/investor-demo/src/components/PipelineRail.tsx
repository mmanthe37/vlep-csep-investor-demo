import { Check } from "lucide-react";
import type { PipelineStage } from "../types";
import type { PipelineStatus } from "../usePipelineDemo";

interface PipelineRailProps {
  stages: PipelineStage[];
  activeStage: number;
  status: PipelineStatus;
}

export function PipelineRail({ stages, activeStage, status }: PipelineRailProps) {
  return (
    <ol className="pipeline-rail" aria-label="Pipeline execution progress">
      {stages.map((stage, index) => {
        const complete = status === "complete" || index < activeStage;
        const active = status === "running" && index === activeStage;
        return (
          <li className={active ? "is-active" : complete ? "is-complete" : ""} key={stage.name}>
            <span className="stage-number" aria-hidden="true">
              {complete ? <Check size={15} /> : stage.number}
            </span>
            <span>{stage.name}</span>
            <small>{active ? "Running" : complete ? "Complete" : "Queued"}</small>
          </li>
        );
      })}
    </ol>
  );
}
