-- 005_phenotype_assertions_features.sql
-- Assertions, support links, temporal feature windows, ontology embeddings, prior weights.

BEGIN;

CREATE TABLE IF NOT EXISTS phenotyping.phenotype_assertions (
  assertion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  phenotype_dimension phenotyping.phenotype_dimension NOT NULL,
  phenotype_label_concept_id UUID REFERENCES ontology.concepts(concept_id) ON DELETE SET NULL,
  phenotype_label_text TEXT NOT NULL,
  effective_start TIMESTAMPTZ NOT NULL,
  effective_end TIMESTAMPTZ,
  confidence_data_quality NUMERIC(5,4) NOT NULL DEFAULT 0.0 CHECK (confidence_data_quality BETWEEN 0 AND 1),
  confidence_recency NUMERIC(5,4) NOT NULL DEFAULT 0.0 CHECK (confidence_recency BETWEEN 0 AND 1),
  confidence_consistency NUMERIC(5,4) NOT NULL DEFAULT 0.0 CHECK (confidence_consistency BETWEEN 0 AND 1),
  posterior_probability NUMERIC(6,5) CHECK (posterior_probability IS NULL OR posterior_probability BETWEEN 0 AND 1),
  final_score NUMERIC(6,5) NOT NULL DEFAULT 0.0 CHECK (final_score BETWEEN 0 AND 1),
  status phenotyping.assertion_status NOT NULL DEFAULT 'active',
  generated_by TEXT NOT NULL DEFAULT 'assertion_builder',
  model_version_id UUID,
  nosology_version_id UUID REFERENCES nosology.framework_versions(nosology_version_id) ON DELETE SET NULL,
  supersedes_assertion_id UUID REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (effective_end IS NULL OR effective_end >= effective_start)
);

CREATE TABLE IF NOT EXISTS phenotyping.assertion_support_events (
  assertion_id UUID NOT NULL REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE CASCADE,
  event_id UUID NOT NULL REFERENCES evidence.ledger_events(event_id) ON DELETE RESTRICT,
  support_role TEXT NOT NULL DEFAULT 'supporting',
  support_weight NUMERIC(6,5) NOT NULL DEFAULT 1.0 CHECK (support_weight BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (assertion_id, event_id)
);

CREATE TABLE IF NOT EXISTS phenotyping.assertion_support_claims (
  assertion_id UUID NOT NULL REFERENCES phenotyping.phenotype_assertions(assertion_id) ON DELETE CASCADE,
  claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE RESTRICT,
  ruleset_id UUID REFERENCES literature.heuristic_rulesets(ruleset_id) ON DELETE SET NULL,
  support_role TEXT NOT NULL DEFAULT 'literature_prior',
  support_weight NUMERIC(6,5) NOT NULL DEFAULT 1.0 CHECK (support_weight BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (assertion_id, claim_id)
);

CREATE TABLE IF NOT EXISTS phenotyping.feature_sets (
  feature_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  version_label TEXT NOT NULL,
  description TEXT,
  embedding_version_id UUID REFERENCES ontology.embedding_versions(embedding_version_id) ON DELETE SET NULL,
  ruleset_id UUID REFERENCES literature.heuristic_rulesets(ruleset_id) ON DELETE SET NULL,
  dimensionality INTEGER NOT NULL CHECK (dimensionality > 0),
  window_days INTEGER NOT NULL DEFAULT 30 CHECK (window_days > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (name, version_label)
);

CREATE TABLE IF NOT EXISTS phenotyping.feature_definitions (
  feature_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feature_set_id UUID NOT NULL REFERENCES phenotyping.feature_sets(feature_set_id) ON DELETE CASCADE,
  feature_name TEXT NOT NULL,
  feature_index INTEGER NOT NULL CHECK (feature_index >= 0),
  feature_dimension phenotyping.phenotype_dimension,
  concept_id UUID REFERENCES ontology.concepts(concept_id) ON DELETE SET NULL,
  aggregation_method TEXT NOT NULL DEFAULT 'tfidf_weighted_pooling',
  decay_lambda DOUBLE PRECISION CHECK (decay_lambda IS NULL OR decay_lambda >= 0),
  is_static BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (feature_set_id, feature_index),
  UNIQUE (feature_set_id, feature_name)
);

CREATE TABLE IF NOT EXISTS phenotyping.feature_weight_priors (
  feature_id UUID NOT NULL REFERENCES phenotyping.feature_definitions(feature_id) ON DELETE CASCADE,
  ruleset_id UUID NOT NULL REFERENCES literature.heuristic_rulesets(ruleset_id) ON DELETE RESTRICT,
  scalar_weight NUMERIC(6,5) NOT NULL CHECK (scalar_weight BETWEEN 0 AND 1),
  derived_from_claim_count INTEGER NOT NULL DEFAULT 0 CHECK (derived_from_claim_count >= 0),
  source_claim_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (feature_id, ruleset_id)
);

CREATE TABLE IF NOT EXISTS phenotyping.temporal_feature_windows (
  feature_window_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  feature_set_id UUID NOT NULL REFERENCES phenotyping.feature_sets(feature_set_id) ON DELETE RESTRICT,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  as_of_time TIMESTAMPTZ NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count >= 0),
  missingness_score NUMERIC(5,4) CHECK (missingness_score IS NULL OR missingness_score BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (patient_id, feature_set_id, window_start, window_end, as_of_time),
  CHECK (window_end > window_start),
  CHECK (as_of_time >= window_end)
);

CREATE TABLE IF NOT EXISTS phenotyping.feature_values (
  feature_window_id UUID NOT NULL REFERENCES phenotyping.temporal_feature_windows(feature_window_id) ON DELETE CASCADE,
  feature_id UUID NOT NULL REFERENCES phenotyping.feature_definitions(feature_id) ON DELETE CASCADE,
  raw_value DOUBLE PRECISION,
  weighted_value DOUBLE PRECISION,
  imputed_value DOUBLE PRECISION,
  imputation_method TEXT,
  source_event_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
  source_claim_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (feature_window_id, feature_id)
);

CREATE TABLE IF NOT EXISTS phenotyping.patient_trajectory_snapshots (
  trajectory_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  feature_set_id UUID NOT NULL REFERENCES phenotyping.feature_sets(feature_set_id) ON DELETE RESTRICT,
  as_of_time TIMESTAMPTZ NOT NULL,
  window_count INTEGER NOT NULL CHECK (window_count >= 0),
  feature_count INTEGER NOT NULL CHECK (feature_count >= 0),
  trajectory_matrix_uri TEXT,
  trajectory_matrix_sha256 TEXT,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMIT;

