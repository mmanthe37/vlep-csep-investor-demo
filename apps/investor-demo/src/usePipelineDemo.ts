import { useCallback, useEffect, useState } from "react";

export type PipelineStatus = "idle" | "running" | "complete";

export function usePipelineDemo(stageCount: number) {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [activeStage, setActiveStage] = useState(-1);
  const [runCount, setRunCount] = useState(0);

  useEffect(() => {
    if (status !== "running") return undefined;
    const timer = window.setTimeout(() => {
      if (activeStage >= stageCount - 1) {
        setStatus("complete");
        setRunCount((count) => count + 1);
        return;
      }
      setActiveStage((stage) => stage + 1);
    }, activeStage < 0 ? 180 : 430);
    return () => window.clearTimeout(timer);
  }, [activeStage, stageCount, status]);

  const run = useCallback(() => {
    setActiveStage(-1);
    setStatus("running");
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setActiveStage(-1);
  }, []);

  return { status, activeStage, runCount, run, reset };
}
