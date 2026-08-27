-- 009_seed_reference_data.sql
-- Minimal reference seed data. Replace version labels with institution-approved releases.

BEGIN;

INSERT INTO ontology.vocabularies (kind, name, version, release_date, uri)
VALUES
  ('SNOMED_CT', 'SNOMED CT', 'placeholder-current', NULL, 'https://www.snomed.org/'),
  ('RxNorm', 'RxNorm', 'placeholder-current', NULL, 'https://www.nlm.nih.gov/research/umls/rxnorm/'),
  ('LOINC', 'LOINC', 'placeholder-current', NULL, 'https://loinc.org/'),
  ('HPO', 'Human Phenotype Ontology', 'placeholder-current', NULL, 'https://hpo.jax.org/'),
  ('OMOP_CONCEPT', 'OMOP Common Data Model Vocabulary', 'placeholder-current', NULL, 'https://ohdsi.github.io/CommonDataModel/')
ON CONFLICT (kind, version) DO NOTHING;

INSERT INTO nosology.framework_versions (
  framework_name,
  version_label,
  authority,
  effective_from,
  is_default,
  status,
  metadata
)
VALUES
  (
    'ILAE epilepsy classification',
    '2017-baseline',
    'ILAE',
    DATE '2017-01-01',
    TRUE,
    'active',
    '{"note":"Baseline seed. Replace with curated local canonical nosology package."}'::jsonb
  )
ON CONFLICT (framework_name, version_label) DO NOTHING;

INSERT INTO literature.heuristic_rulesets (
  name,
  version_label,
  status,
  description,
  rules_json
)
VALUES
  (
    'VLEP deterministic provenance tiering',
    'v0.1',
    'draft',
    'Ruleset captures causal/large cohort, retrospective cohort, case-series, and excluded evidence tiers; adjust for rare disease adaptive thresholds when approved.',
    '{
      "tier_1": {
        "causal_methods": ["Mendelian Randomization", "LDSC"],
        "prospective_or_rct": {"n_min": 200, "p_value_max": 0.01}
      },
      "tier_2": {
        "designs": ["retrospective", "cross-sectional", "cohort"],
        "n_min": 50,
        "p_value_max": 0.05
      },
      "tier_3": {
        "designs": ["observational case-series"],
        "n_min": 20,
        "n_max_exclusive": 50
      },
      "excluded": {
        "n_max_exclusive": 20,
        "note": "Case reports and underpowered claims excluded unless rare-disease adaptive rules are explicitly enabled."
      },
      "weights": {
        "TIER_1": 1.0,
        "TIER_2": 0.6,
        "TIER_3": 0.2,
        "TIER_4": 0.1,
        "EXCLUDED": 0.0
      }
    }'::jsonb
  )
ON CONFLICT (name, version_label) DO NOTHING;

INSERT INTO phenotyping.feature_sets (
  name,
  version_label,
  description,
  dimensionality,
  window_days,
  metadata
)
VALUES
  (
    'VLEP MVP phenotype vector',
    'v0.1',
    'MVP feature space for seizure type, etiology, syndrome, biomarkers, comorbidities, treatment response, and drug resistance.',
    256,
    30,
    '{"aggregation":"tfidf_weighted_pooling","decay":"feature_specific_exponential","imputation":"sparse_gaussian_process"}'::jsonb
  )
ON CONFLICT (name, version_label) DO NOTHING;

COMMIT;
