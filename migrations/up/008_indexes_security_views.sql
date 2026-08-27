-- 008_indexes_security_views.sql
-- Indexes, search acceleration, audit views, and safe time-dependent helper views.

BEGIN;

-- Core and ingestion indexes.
CREATE INDEX IF NOT EXISTS idx_patients_source_hash_trgm ON core.patients USING GIN (source_patient_hash gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cohort_memberships_patient ON core.cohort_memberships(patient_id);
CREATE INDEX IF NOT EXISTS idx_raw_resources_patient_created ON ingestion.raw_resources(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_resources_type_status ON ingestion.raw_resources(resource_type, status);

-- Ontology indexes.
CREATE INDEX IF NOT EXISTS idx_concepts_vocab_code ON ontology.concepts(vocabulary_id, code);
CREATE INDEX IF NOT EXISTS idx_concepts_display_trgm ON ontology.concepts USING GIN (display gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_concepts_metadata_gin ON ontology.concepts USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_concept_edges_parent ON ontology.concept_edges(parent_concept_id);
CREATE INDEX IF NOT EXISTS idx_concept_edges_child ON ontology.concept_edges(child_concept_id);

-- Literature indexes.
CREATE INDEX IF NOT EXISTS idx_documents_pmid ON literature.documents(pmid);
CREATE INDEX IF NOT EXISTS idx_documents_pmcid ON literature.documents(pmcid);
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm ON literature.documents USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_document_sections_document ON literature.document_sections(document_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_claims_subject_text_trgm ON literature.phenotype_claims USING GIN (subject_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_claims_object_text_trgm ON literature.phenotype_claims USING GIN (object_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_claims_context_gin ON literature.phenotype_claims USING GIN (relation_context);
CREATE INDEX IF NOT EXISTS idx_claims_source_offsets ON literature.phenotype_claims(source_document_id, source_start_offset, source_end_offset);
CREATE INDEX IF NOT EXISTS idx_claim_tiering_tier ON literature.claim_tiering_results(tier, scalar_weight DESC);
CREATE INDEX IF NOT EXISTS idx_corpus_claims_claim ON literature.corpus_claims(claim_id);

-- Ledger indexes.
CREATE INDEX IF NOT EXISTS idx_ledger_patient_observed ON evidence.ledger_events(patient_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_domain_observed ON evidence.ledger_events(domain, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_validation_status ON evidence.ledger_events(validation_status);
CREATE INDEX IF NOT EXISTS idx_ledger_data_element_gin ON evidence.ledger_events USING GIN (data_element);
CREATE INDEX IF NOT EXISTS idx_ledger_normalized_codes_gin ON evidence.ledger_events USING GIN (normalized_codes);
CREATE INDEX IF NOT EXISTS idx_ledger_provenance_gin ON evidence.ledger_events USING GIN (provenance);
CREATE INDEX IF NOT EXISTS idx_ledger_supersedes ON evidence.ledger_events(supersedes_event_id);
CREATE INDEX IF NOT EXISTS idx_ledger_hash_self ON evidence.ledger_events(hash_self);

-- Phenotyping indexes.
CREATE INDEX IF NOT EXISTS idx_assertions_patient_dim_status ON phenotyping.phenotype_assertions(patient_id, phenotype_dimension, status);
CREATE INDEX IF NOT EXISTS idx_assertions_effective ON phenotyping.phenotype_assertions(patient_id, effective_start, effective_end);
CREATE INDEX IF NOT EXISTS idx_assertions_score ON phenotyping.phenotype_assertions(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_feature_windows_patient_time ON phenotyping.temporal_feature_windows(patient_id, feature_set_id, window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_feature_values_feature ON phenotyping.feature_values(feature_id);
CREATE INDEX IF NOT EXISTS idx_trajectory_patient_asof ON phenotyping.patient_trajectory_snapshots(patient_id, as_of_time DESC);

-- Modeling and CSEP indexes.
CREATE INDEX IF NOT EXISTS idx_model_versions_status ON modeling.model_versions(status, family);
CREATE INDEX IF NOT EXISTS idx_lpa_runs_status ON modeling.lpa_runs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_latent_patient_asof ON modeling.latent_state_sequences(patient_id, as_of_time DESC);
CREATE INDEX IF NOT EXISTS idx_hazards_patient_event ON modeling.time_to_event_hazards(patient_id, event_type, as_of_time DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_patient_type ON modeling.predictions(patient_id, prediction_type, as_of_time DESC);
CREATE INDEX IF NOT EXISTS idx_csep_patient_asof ON csep.profiles(patient_id, as_of_time DESC);
CREATE INDEX IF NOT EXISTS idx_csep_predictive_outputs_gin ON csep.profiles USING GIN (predictive_outputs);
CREATE INDEX IF NOT EXISTS idx_csep_uncertainty_gin ON csep.profiles USING GIN (uncertainty);

-- Nosology indexes.
CREATE INDEX IF NOT EXISTS idx_taxonomy_terms_version_dim ON nosology.taxonomy_terms(nosology_version_id, dimension);
CREATE INDEX IF NOT EXISTS idx_taxonomy_terms_display_trgm ON nosology.taxonomy_terms USING GIN (display gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_resolution_rules_version_priority ON nosology.resolution_rules(nosology_version_id, active, priority);

-- Governance/review indexes.
CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review.review_tasks(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_issue_reports_status ON review.issue_reports(status, severity, created_at);
CREATE INDEX IF NOT EXISTS idx_access_logs_patient ON governance.access_logs(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_events_patient ON governance.alert_events(patient_id, displayed_at DESC);

-- Safe query helper: active ledger events up to current time, excluding superseded events.
CREATE OR REPLACE VIEW evidence.active_ledger_events AS
SELECT le.*
FROM evidence.ledger_events le
WHERE le.validation_status IN ('normalized', 'verified')
  AND NOT EXISTS (
    SELECT 1
    FROM evidence.ledger_events newer
    WHERE newer.supersedes_event_id = le.event_id
      AND newer.validation_status IN ('normalized', 'verified')
  );

-- Latest CSEP profile for each patient and nosology/model combination.
CREATE OR REPLACE VIEW csep.latest_profiles AS
SELECT DISTINCT ON (patient_id, nosology_version_id, model_version_id)
  *
FROM csep.profiles
WHERE status = 'active'
ORDER BY patient_id, nosology_version_id, model_version_id, as_of_time DESC, generated_at DESC;

-- Claim audit view joins exact offsets, tier, and evidence metadata.
CREATE OR REPLACE VIEW literature.claim_audit_view AS
SELECT
  pc.claim_id,
  pc.claim_key,
  pc.subject_text,
  pc.predicate,
  pc.object_text,
  pc.source_document_id,
  d.title AS source_title,
  d.pmid,
  d.pmcid,
  d.doi,
  pc.source_start_offset,
  pc.source_end_offset,
  pc.source_sentence,
  cem.study_design,
  cem.n_subjects,
  cem.p_value,
  cem.causal_method,
  ctr.tier,
  ctr.scalar_weight,
  ctr.tier_rationale,
  ctr.ruleset_id
FROM literature.phenotype_claims pc
JOIN literature.documents d ON d.document_id = pc.source_document_id
LEFT JOIN literature.claim_evidence_metadata cem ON cem.claim_id = pc.claim_id
LEFT JOIN literature.claim_tiering_results ctr ON ctr.claim_id = pc.claim_id;

-- Enable RLS on patient-sensitive tables. Application roles should define policies after deployment.
ALTER TABLE core.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence.ledger_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE phenotyping.phenotype_assertions ENABLE ROW LEVEL SECURITY;
ALTER TABLE csep.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE modeling.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.access_logs ENABLE ROW LEVEL SECURITY;

COMMIT;

