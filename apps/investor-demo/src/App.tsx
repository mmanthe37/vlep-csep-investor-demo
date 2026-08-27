import { useCallback, useEffect, useState } from "react";
import { Architecture } from "./components/Architecture";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Hero } from "./components/Hero";
import { Roadmap } from "./components/Roadmap";
import { Validation } from "./components/Validation";
import { Workbench } from "./components/Workbench";
import type { DemoBundle, FrameworkKey } from "./types";
import { usePipelineDemo } from "./usePipelineDemo";

export default function App() {
  const [bundle, setBundle] = useState<DemoBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [framework, setFramework] = useState<FrameworkKey>("ILAE-2025");
  const pipeline = usePipelineDemo(6);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}demo-bundle.json`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Demo bundle failed to load (${response.status}).`);
        return response.json() as Promise<DemoBundle>;
      })
      .then(setBundle)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "The demo bundle could not be loaded.");
      });
    return () => controller.abort();
  }, []);

  const runAndScroll = useCallback(() => {
    document.getElementById("live-demo")?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(pipeline.run, 320);
  }, [pipeline.run]);

  if (error) {
    return <main className="load-state"><h1>VLEP</h1><p>{error}</p><p>Run the demo-bundle export script before starting the site.</p></main>;
  }
  if (!bundle) {
    return <main className="load-state" aria-live="polite"><h1>VLEP</h1><p>Loading deterministic research fixture…</p></main>;
  }

  return (
    <>
      <Header onRun={runAndScroll} />
      <main>
        <Hero onRun={runAndScroll} />
        <div className="version-statement section-shell">
          <h2>Evidence stays fixed. Interpretation becomes version-aware.</h2>
          <p>The same ledger is resolved under each framework; conditional terminology changes remain visible and reviewable.</p>
        </div>
        <Workbench
          bundle={bundle}
          framework={framework}
          onFrameworkChange={setFramework}
          status={pipeline.status}
          activeStage={pipeline.activeStage}
          runCount={pipeline.runCount}
          onRun={pipeline.run}
          onReset={pipeline.reset}
        />
        <Architecture />
        <Validation />
        <Roadmap onRun={runAndScroll} />
      </main>
      <Footer bundle={bundle} />
    </>
  );
}
