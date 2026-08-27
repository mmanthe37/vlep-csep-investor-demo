import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Check,
  ChevronDown,
  Clipboard,
  Dna,
  FileText,
  FlaskConical,
  HeartPulse,
  Image as ImageIcon,
  NotebookPen,
  Pill,
  Play,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { DemoBundle, FrameworkKey, LedgerEvent, MappingDecision, PipelineRun } from "../types";
import type { PipelineStatus } from "../usePipelineDemo";
import { PipelineRail } from "./PipelineRail";

interface WorkbenchProps {
  bundle: DemoBundle;
  framework: FrameworkKey;
  onFrameworkChange: (framework: FrameworkKey) => void;
  status: PipelineStatus;
  activeStage: number;
  runCount: number;
  onRun: () => void;
  onReset: () => void;
}

const dimensionIcons = {
  seizure: Activity,
  etiology: Dna,
  syndrome: BrainCircuit,
  biomarkers: FlaskConical,
  comorbidity: HeartPulse,
  treatment: Pill,
};

const sourceIcons = {
  clinical_note: FileText,
  eeg: Activity,
  imaging: ImageIcon,
  medication: Pill,
  patient_diary: NotebookPen,
};

export function Workbench({
  bundle,
  framework,
  onFrameworkChange,
  status,
  activeStage,
  runCount,
  onRun,
  onReset,
}: WorkbenchProps) {
  const run = bundle.runs[framework];
  const targetMapping = bundle.runs["ILAE-2025"].mappings[0];
  const [selectedEventId, setSelectedEventId] = useState(run.ledger[1]?.event_id ?? run.ledger[0]?.event_id);
  const [auditOpen, setAuditOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const selectedEvent = useMemo(
    () => run.ledger.find((event) => event.event_id === selectedEventId) ?? run.ledger[0],
    [run.ledger, selectedEventId],
  );

  const copyCaseId = async () => {
    await navigator.clipboard.writeText(bundle.case.case_id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <section className="workbench-section section-shell" id="live-demo">
      <div className="section-heading workbench-heading">
        <div>
          <h2>Run the pipeline. Inspect every transformation.</h2>
          <p>A deterministic demonstration of evidence ingestion, profile resolution, and nosology-aware reinterpretation.</p>
        </div>
        <div className="workbench-actions">
          <button className="button button-primary" type="button" onClick={onRun} disabled={status === "running"}>
            <Play size={17} fill="currentColor" aria-hidden="true" />
            {status === "running" ? "Running…" : "Run pipeline"}
          </button>
          <button className="button button-secondary" type="button" onClick={onReset}>
            <RotateCcw size={17} aria-hidden="true" /> Reset
          </button>
        </div>
      </div>

      <PipelineRail stages={run.stages} activeStage={activeStage} status={status} />

      <div className="workbench-grid">
        <aside className="case-rail" aria-label="Synthetic case sources">
          <div className="panel-title">Synthetic case</div>
          <dl className="case-meta">
            <div>
              <dt>Case ID (de-identified)</dt>
              <dd>
                <code>{bundle.case.case_id}</code>
                <button className="icon-button" type="button" onClick={copyCaseId} aria-label="Copy case ID">
                  {copied ? <Check size={15} /> : <Clipboard size={15} />}
                </button>
              </dd>
            </div>
            <div>
              <dt>As-of (UTC)</dt>
              <dd>{formatDate(bundle.case.as_of_time)}</dd>
            </div>
          </dl>
          <div className="source-label">Source events · chronological</div>
          <ol className="source-timeline">
            {bundle.case.evidence.map((event) => {
              const Icon = sourceIcons[event.domain as keyof typeof sourceIcons] ?? FileText;
              return (
                <li key={event.evidence_id}>
                  <Icon size={16} aria-hidden="true" />
                  <div>
                    <time>{formatShortDate(event.observed_at)}</time>
                    <strong>{domainLabel(event.domain)}</strong>
                    <small>{event.source_reference.replace("Synthetic ", "")}</small>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="no-phi">No PHI · Generated fixture</div>
        </aside>

        <div className="ledger-panel">
          <div className="panel-title-row">
            <div>
              <h3>Evidence ledger</h3>
              <p>Append-only events with source-bound canonical concepts.</p>
            </div>
            <span className="verified-label"><ShieldCheck size={15} /> Chain verified</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Seq</th>
                  <th>Observed</th>
                  <th>Domain</th>
                  <th>Normalized concept</th>
                  <th>Source</th>
                  <th>Integrity</th>
                </tr>
              </thead>
              <tbody>
                {run.ledger.map((event) => (
                  <LedgerRow
                    event={event}
                    key={event.event_id}
                    selected={event.event_id === selectedEvent.event_id}
                    onSelect={() => setSelectedEventId(event.event_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <ProvenanceDetail event={selectedEvent} />
        </div>

        <aside className="profile-panel">
          <div className="panel-title-row compact">
            <h3>Current-state epilepsy profile</h3>
          </div>
          <label className="framework-select">
            <span>Framework</span>
            <select value={framework} onChange={(event) => onFrameworkChange(event.target.value as FrameworkKey)}>
              <option value="ILAE-2017">ILAE 2017</option>
              <option value="ILAE-2025">ILAE 2025</option>
            </select>
            <ChevronDown size={15} aria-hidden="true" />
          </label>
          <div className="profile-dimensions">
            {run.profile.dimensions.map((dimension) => {
              const Icon = dimensionIcons[dimension.dimension as keyof typeof dimensionIcons] ?? Activity;
              return (
                <div className="profile-dimension" key={dimension.dimension}>
                  <Icon size={18} aria-hidden="true" />
                  <div>
                    <strong>{capitalize(dimension.dimension)}</strong>
                    <span>{dimension.label}</span>
                  </div>
                  <div className="score">
                    <small>demo score</small>
                    {dimension.demo_score.toFixed(2)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="resolution-box">
            <strong>Resolution status</strong>
            <span>{run.profile.resolution_status.resolved} resolved</span>
            <span className="review-count">{run.profile.resolution_status.review_required} review required</span>
          </div>
          <div className="profile-integrity">
            <div><ShieldCheck size={16} /> <strong>Profile integrity</strong> Verified</div>
            <code title={run.profile.profile_hash}>{truncateHash(run.profile.profile_hash, 30)}</code>
          </div>
          <p className="score-notice">{run.profile.score_notice}</p>
        </aside>
      </div>

      <InterpretationDiff mapping={targetMapping} onOpenAudit={() => setAuditOpen(true)} />

      <div className="execution-log" aria-live="polite">
        <strong>Execution log</strong>
        <span>Pipeline run <code>{run.run_id}</code></span>
        <span>Deterministic seed <code>{truncateHash(run.deterministic_seed, 16)}</code></span>
        <span>Engine <code>{run.engine_version}</code></span>
        <span className={status === "complete" ? "complete" : ""}>
          {status === "complete" ? <Check size={15} /> : null}
          {status === "idle" ? "Ready" : status === "running" ? `Stage ${Math.max(activeStage + 1, 1)} of 6` : `Completed · run ${runCount}`}
        </span>
      </div>

      {auditOpen ? <AuditDialog mapping={targetMapping} run={run} onClose={() => setAuditOpen(false)} /> : null}
    </section>
  );
}

function LedgerRow({ event, selected, onSelect }: { event: LedgerEvent; selected: boolean; onSelect: () => void }) {
  const primaryConcept = event.concepts[0];
  return (
    <tr className={selected ? "selected" : ""} onClick={onSelect}>
      <td><button type="button" onClick={onSelect} aria-label={`Inspect event ${event.seq}`}>{String(event.seq).padStart(3, "0")}</button></td>
      <td>{formatTime(event.observed_at)}</td>
      <td>{domainLabel(event.domain)}</td>
      <td>{primaryConcept?.display ?? "Review required"}</td>
      <td>{shortSource(event.source_reference)}</td>
      <td><span className="hash-ok"><Check size={14} /> {truncateHash(event.hash_self, 10)}</span></td>
    </tr>
  );
}

function ProvenanceDetail({ event }: { event: LedgerEvent }) {
  const concept = event.concepts[0];
  return (
    <div className="provenance-detail">
      <div>
        <small>Raw term · as observed</small>
        <strong>{event.raw_text}</strong>
        <small>Normalized term</small>
        <strong className="teal">{concept?.display ?? "Unmapped"}</strong>
      </div>
      <div>
        <small>Confidence components</small>
        <dl>
          <div><dt>Source confidence</dt><dd>{event.source_confidence.toFixed(2)}</dd></div>
          <div><dt>Normalization rule</dt><dd>{concept?.normalization_rule ?? "—"}</dd></div>
          <div><dt>Composite demo score</dt><dd>{concept?.confidence.toFixed(2) ?? "—"}</dd></div>
        </dl>
      </div>
      <div>
        <small>Source reference</small>
        <strong>{event.source_reference}</strong>
        <small>Integrity</small>
        <code>prev {truncateHash(event.hash_prev, 24)}</code>
        <code>self {truncateHash(event.hash_self, 24)}</code>
      </div>
    </div>
  );
}

function InterpretationDiff({ mapping, onOpenAudit }: { mapping: MappingDecision; onOpenAudit: () => void }) {
  return (
    <div className="interpretation-diff">
      <div className="diff-heading">
        <h3>Interpretation diff</h3>
        <span>Nosology-aware · original evidence preserved</span>
      </div>
      <div className="term-box">
        <small>ILAE 2017 · source framework</small>
        <strong>{mapping.source_term}</strong>
        <code>{mapping.internal_code}</code>
      </div>
      <div className="mapping-arrow">
        <ArrowRight aria-hidden="true" />
        <strong>Conditional</strong>
        <span>Requires reviewer</span>
      </div>
      <div className="term-box target">
        <small>ILAE 2025 · target framework</small>
        <strong>{mapping.target_term}</strong>
        <code>{mapping.internal_code}</code>
      </div>
      <div className="diff-reason">
        <strong>Why this changed</strong>
        <p>{mapping.rationale}</p>
        <button className="button button-tertiary" type="button" onClick={onOpenAudit}>Open audit trace</button>
      </div>
    </div>
  );
}

function AuditDialog({ mapping, run, onClose }: { mapping: MappingDecision; run: PipelineRun; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="audit-dialog" role="dialog" aria-modal="true" aria-labelledby="audit-title" onMouseDown={(event) => event.stopPropagation()}>
        <button ref={closeButtonRef} className="dialog-close" type="button" onClick={onClose} aria-label="Close audit trace"><X /></button>
        <h3 id="audit-title">Nosology mapping audit trace</h3>
        <p>Every reinterpretation records the source term, target term, decision status, rationale, and profile integrity hash.</p>
        <dl className="audit-grid">
          <div><dt>Mapping ID</dt><dd><code>{mapping.mapping_id}</code></dd></div>
          <div><dt>Status</dt><dd>{mapping.status} · human review required</dd></div>
          <div><dt>Source</dt><dd>{mapping.source_framework} · {mapping.source_term}</dd></div>
          <div><dt>Target</dt><dd>{mapping.target_framework} · {mapping.target_term}</dd></div>
          <div><dt>Evidence policy</dt><dd>Original event text and hash chain remain unchanged.</dd></div>
          <div><dt>Profile hash</dt><dd><code>{run.profile.profile_hash}</code></dd></div>
        </dl>
        <div className="dialog-note">This demonstrates software traceability only. It does not validate the clinical correctness of the mapping.</div>
      </section>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(value));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value));
}

function domainLabel(domain: string) {
  const labels: Record<string, string> = { clinical_note: "Clinical note", eeg: "EEG finding", imaging: "MRI finding", medication: "Medication trial", patient_diary: "Patient diary" };
  return labels[domain] ?? capitalize(domain);
}

function shortSource(value: string) {
  return value.replace("Synthetic ", "").replace("study ", "").replace("record ", "").replace("entry ", "");
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function truncateHash(value: string, length: number) {
  if (value.length <= length) return value;
  return `${value.slice(0, Math.max(6, length - 5))}…${value.slice(-4)}`;
}
