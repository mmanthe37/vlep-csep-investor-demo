-- 006_lpa_modeling_csep.sql
-- LPA models, runs, predictions, CSEP snapshots and traceability.

BEGIN;

CREATE TABLE IF NOT EXISTS modeling.model_versions (
  model_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  family modeling.model_family NOT NULL,
  version_label TEXT NOT NULL,
  training_dataset_uri TEXT,
  training_dataset_sha256 TEXT,
  feature_set_id UUID REFERENCES phenotyping.feature_sets(feature_set_id) ON DELETE SET NULL,
  corpus_release_id UUID REFERENCES literature.corpus_releases(corpus_release_id) ON DELETE SET NULL,
  nosology_version_id UUID REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE SET NULL,
  artifact_uri TEXT,
  artifact_sha256 TEXT,
  hyperparameters JSONB NOT NULL DEFAULT '{}'::jsonb,
  model_card JSONB NOT NULL DEFAULT '{}'::jsonb,
  trained_at TIMESTAMPTZ,
  promoted_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'registered',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version_label)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_assertion_model_version'
      AND conrelid = 'phenotyping.phenotype_assertions'::regclass
  ) THEN
    ALTER TABLE phenotyping.phenotype_assertions
      ADD CONSTRAINT fk_assertion_model_version
      FOREIGN KEY (model_version_id) REFERENCES modeling.model_versions(model_version_id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS modeling.lpa_runs (
  lpa_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_kind TEXT NOT NULL,
  model_version_id UUID REFERENCES modeling.model_versions(model_version_id) ON DELETE SET NULL,
  feature_set_id UUID REFERENCES phenotyping.feature_sets(feature_set_id) ON DELETE SET NULL,
  corpus_release_id UUID REFERENCES literature.corpus_releases(corpus_release_id) ON DELETE SET NULL,
  nosology_version_id UUID REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'running',
  patients_processed INTEGER NOT NULL DEFAULT 0 CHECK (patients_processed >= 0),
  error_summary TEXT,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS modeling.latent_state_sequences (
  latent_state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lpa_run_id UUID NOT NULL REFERENCES modeling.lpa_runs(lpa_run_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  as_of_time TIMESTAMPTZ NOT NULL,
  state_label TEXT NOT NULL,
  state_probability NUMERIC(6,5) NOT NULL CHECK (state_probability BETWEEN 0 AND 1),
  state_index INTEGER CHECK (state_index IS NULL OR state_index >= 0),
  window_start TIMESTAMPTZ,
  window_end TIMESTAMPTZ,
  viterbi_path JSONB,
  emission_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS modeling.time_to_event_hazards (
  hazard_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lpa_run_id UUID NOT NULL REFERENCES modeling.lpa_runs(lpa_run_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  as_of_time TIMESTAMPTZ NOT NULL,
  horizon_days INTEGER NOT NULL CHECK (horizon_days > 0),
  hazard_value DOUBLE PRECISION NOT NULL CHECK (hazard_value >= 0),
  survival_probability NUMERIC(6,5) CHECK (survival_probability IS NULL OR survival_probability BETWEEN 0 AND 1),
  cumulative_incidence NUMERIC(6,5) CHECK (cumulative_incidence IS NULL OR cumulative_incidence BETWEEN 0 AND 1),
  feature_contributions JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS modeling.predictions (
  prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lpa_run_id UUID NOT NULL REFERENCES modeling.lpa_runs(lpa_run_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  prediction_type TEXT NOT NULL,
  as_of_time TIMESTAMPTZ NOT NULL,
  horizon_days INTEGER,
  value_numeric DOUBLE PRECISION,
  value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  probability NUMERIC(6,5) CHECK (probability IS NULL OR probability BETWEEN 0 AND 1),
  uncertainty JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS modeling.validation_metric_results (
  metric_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id UUID REFERENCES modeling.model_versions(model_version_id) ON DELETE CASCADE,
  lpa_run_id UUID REFERENCES modeling.lpa_runs(lpa_run_id) ON DELETE CASCADE,
  cohort_id UUID REFERENCES core.cohorts(cohort_id) ON DELETE SET NULL,
  metric_name TEXT NOT NULL,
  metric_value DOUBLE PRECISION NOT NULL,
  metric_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nosology.taxonomy_terms (
  taxonomy_term_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nosology_version_id UUID NOT NULL REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE CASCADE,
  dimension phenotyping.phenotype_dimension NOT NULL,
  code TEXT NOT NULL,
  display TEXT NOT NULL,
  parent_code TEXT,
  concept_id UUID REFERENCES ontology.concepts(concept_id) ON DELETE SET NULL,
  definition TEXT,
  age_constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
  rule_expression JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (nosology_version_id, dimension, code)
);

CREATE TABLE IF NOT EXISTS nosology.taxonomy_edges (
  taxonomy_edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nosology_version_id UUID NOT NULL REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE CASCADE,
  parent_term_id UUID NOT NULL REFERENCES nosology.taxonomy_terms(taxonomy_term_id) ON DELETE CASCADE,
  child_term_id UUID NOT NULL REFERENCES nosology.taxonomy_terms(taxonomy_term_id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'is_a',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (parent_term_id, child_term_id, relation)
);

CREATE TABLE IF NOT EXISTS nosology.resolution_rules (
  resolution_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nosology_version_id UUID NOT NULL REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE CASCADE,
  rule_name TEXT NOT NULL,
  applies_to_dimension phenotyping.phenotype_dimension,
  priority INTEGER NOT NULL DEFAULT 100,
  rule_expression JSONB NOT NULL,
  action JSONB NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (nosology_version_id, rule_name)
);

CREATE TABLE IF NOT EXISTS nosology.reinterpretation_jobs (
  reinterpretation_job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_nosology_version_id UUID REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE SET NULL,
  target_nosology_version_id UUID NOT NULL REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE RESTRICT,
  cohort_id UUID REFERENCES core.cohorts(cohort_id) ON DELETE SET NULL,
  requested_by TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'queued',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS nosology.reinterpretation_results (
  reinterpretation_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reinterpretation_job_id UUID NOT NULL REFERENCES nosology.reinterpretation_jobs(reinterpretation_job_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  source_csep_id UUID,
  target_csep_id UUID,
  changes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS csep.profiles (
  csep_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  as_of_time TIMESTAMPTZ NOT NULL,
  nosology_version_id UUID NOT NULL REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE RESTRICT,
  model_version_id UUID REFERENCES modeling.model_versions(model_version_id) ON DELETE SET NULL,
  lpa_run_id UUID REFERENCES modeling.lpa_runs(lpa_run_id) ON DELETE SET NULL,
  seizure_type_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
  etiology_ranked_confidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  epilepsy_syndrome JSONB NOT NULL DEFAULT '{}'::jsonb,
  biomarker_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  comorbidity_burden JSONB NOT NULL DEFAULT '{}'::jsonb,
  treatment_response JSONB NOT NULL DEFAULT '{}'::jsonb,
  predictive_outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
  uncertainty JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  profile_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (patient_id, as_of_time, nosology_version_id, model_version_id)
);

CREATE TABLE IF NOT EXISTS csep.profile_assertion_trace (
  csep_id UUID NOT NULL REFERENCES csep.profiles(csep_id) ON DELETE CASCADE,
  assertion_id UUID NOT NULL REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE RESTRICT,
  trace_role TEXT NOT NULL DEFAULT 'supporting',
  contribution_weight NUMERIC(6,5) CHECK (contribution_weight IS NULL OR contribution_weight BETWEEN 0 AND 1),
  PRIMARY KEY (csep_id, assertion_id)
);

CREATE TABLE IF NOT EXISTS csep.profile_event_trace (
  csep_id UUID NOT NULL REFERENCES csep.profiles(csep_id) ON DELETE CASCADE,
  event_id UUID NOT NULL REFERENCES evidence.ledger_events(event_id) ON DELETE RESTRICT,
  trace_role TEXT NOT NULL DEFAULT 'supporting',
  PRIMARY KEY (csep_id, event_id)
);

CREATE TABLE IF NOT EXISTS csep.profile_claim_trace (
  csep_id UUID NOT NULL REFERENCES csep.profiles(csep_id) ON DELETE CASCADE,
  claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE RESTRICT,
  trace_role TEXT NOT NULL DEFAULT 'literature_prior',
  contribution_weight NUMERIC(6,5) CHECK (contribution_weight IS NULL OR contribution_weight BETWEEN 0 AND 1),
  PRIMARY KEY (csep_id, claim_id)
);

COMMIT;

