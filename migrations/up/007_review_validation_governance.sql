-- 007_review_validation_governance.sql
-- Review tasks, source verification, issue reports, validation cohorts, governance audit logs and alerts.

BEGIN;

CREATE TABLE IF NOT EXISTS review.review_tasks (
  review_task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type TEXT NOT NULL,
  assigned_to TEXT,
  assigned_role TEXT,
  priority INTEGER NOT NULL DEFAULT 100,
  claim_id UUID REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  assertion_id UUID REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE CASCADE,
  csep_id UUID REFERENCES csep.profiles(csep_id) ON DELETE CASCADE,
  event_id UUID REFERENCES evidence.ledger_events(event_id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  due_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS review.review_decisions (
  review_decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  review_task_id UUID NOT NULL REFERENCES review.review_tasks(review_task_id) ON DELETE CASCADE,
  decision review.review_decision NOT NULL,
  reviewer_id TEXT NOT NULL,
  decision_reason TEXT,
  confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS review.source_text_verifications (
  verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  verifier_id TEXT NOT NULL,
  offset_verified BOOLEAN NOT NULL,
  triple_verified BOOLEAN NOT NULL,
  negation_temporal_context_verified BOOLEAN NOT NULL DEFAULT FALSE,
  notes TEXT,
  verified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review.issue_reports (
  issue_report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reporter_id TEXT,
  reporter_role TEXT,
  issue_type TEXT NOT NULL,
  severity governance.alert_severity NOT NULL DEFAULT 'moderate',
  claim_id UUID REFERENCES literature.phenotype_claims(claim_id) ON DELETE SET NULL,
  assertion_id UUID REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE SET NULL,
  csep_id UUID REFERENCES csep.profiles(csep_id) ON DELETE SET NULL,
  event_id UUID REFERENCES evidence.ledger_events(event_id) ON DELETE SET NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  resolution TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS review.adjudications (
  adjudication_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issue_report_id UUID REFERENCES review.issue_reports(issue_report_id) ON DELETE CASCADE,
  adjudicator_id TEXT NOT NULL,
  adjudication_result TEXT NOT NULL,
  rationale TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS review.validation_cohorts (
  validation_cohort_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cohort_id UUID REFERENCES core.cohorts(cohort_id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  validation_phase TEXT NOT NULL,
  n_target INTEGER CHECK (n_target IS NULL OR n_target >= 0),
  n_actual INTEGER CHECK (n_actual IS NULL OR n_actual >= 0),
  protocol_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (name, validation_phase)
);

CREATE TABLE IF NOT EXISTS review.validation_observations (
  validation_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  validation_cohort_id UUID NOT NULL REFERENCES review.validation_cohorts(validation_cohort_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  outcome_name TEXT NOT NULL,
  outcome_time TIMESTAMPTZ,
  outcome_value JSONB NOT NULL,
  adjudicated_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS governance.access_logs (
  access_log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id TEXT NOT NULL,
  actor_role TEXT,
  action TEXT NOT NULL,
  resource_schema TEXT,
  resource_table TEXT,
  resource_id UUID,
  patient_id UUID REFERENCES core.patients(patient_id) ON DELETE SET NULL,
  access_reason TEXT,
  request_id TEXT,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS governance.alert_events (
  alert_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  csep_id UUID REFERENCES csep.profiles(csep_id) ON DELETE SET NULL,
  alert_type TEXT NOT NULL,
  severity governance.alert_severity NOT NULL,
  interruptive BOOLEAN NOT NULL DEFAULT FALSE,
  rationale TEXT,
  displayed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_at TIMESTAMPTZ,
  acknowledged_by TEXT,
  outcome TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS governance.data_quality_runs (
  data_quality_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_name TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'running',
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  findings JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS governance.model_drift_runs (
  model_drift_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id UUID NOT NULL REFERENCES modeling.model_versions(model_version_id) ON DELETE CASCADE,
  cohort_id UUID REFERENCES core.cohorts(cohort_id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  drift_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  fairness_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'running',
  recommendation TEXT
);

COMMIT;

