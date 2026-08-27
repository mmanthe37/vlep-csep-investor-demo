export type FrameworkKey = "ILAE-2017" | "ILAE-2025";

export interface DemoConcept {
  internal_code: string;
  display: string;
  dimension: string;
  confidence: number;
  normalization_rule: string;
}

export interface LedgerEvent {
  seq: number;
  event_id: string;
  observed_at: string;
  domain: string;
  raw_text: string;
  source_reference: string;
  source_confidence: number;
  normalization_status: string;
  concepts: DemoConcept[];
  hash_prev: string;
  hash_self: string;
  integrity: string;
}

export interface ProfileDimension {
  dimension: string;
  label: string;
  internal_codes: string[];
  demo_score: number;
  supporting_event_ids: string[];
  review_required: boolean;
}

export interface MappingDecision {
  mapping_id: string;
  source_framework: string;
  target_framework: string;
  internal_code: string;
  source_term: string;
  target_term: string;
  status: "exact" | "conditional" | "manual_review";
  rationale: string;
  original_evidence_preserved: boolean;
}

export interface PipelineStage {
  number: number;
  name: string;
  status: string;
  output: string;
}

export interface PipelineRun {
  run_id: string;
  run_hash: string;
  deterministic_seed: string;
  engine_version: string;
  case_id: string;
  as_of_time: string;
  framework: FrameworkKey;
  fixture_type: string;
  stages: PipelineStage[];
  ledger: LedgerEvent[];
  ledger_verified: boolean;
  ledger_head: string;
  profile: {
    profile_id: string;
    profile_hash: string;
    framework: FrameworkKey;
    framework_label: string;
    dimensions: ProfileDimension[];
    resolution_status: { resolved: number; review_required: number };
    integrity: string;
    score_notice: string;
  };
  mappings: MappingDecision[];
  limitations: string[];
}

export interface DemoBundle {
  schema_version: string;
  product: string;
  bundle_hash: string;
  research_only: boolean;
  case: {
    case_id: string;
    as_of_time: string;
    fixture_type: string;
    fixture_version: string;
    description: string;
    evidence: Array<{
      evidence_id: string;
      observed_at: string;
      domain: string;
      raw_text: string;
      source_reference: string;
      source_confidence: number;
    }>;
  };
  runs: Record<FrameworkKey, PipelineRun>;
  sources: Array<{ title: string; url: string }>;
}
