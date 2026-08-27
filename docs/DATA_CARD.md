# Data Card - Synthetic Case SYN-0042

## Dataset

One fictional, machine-readable fixture created for software demonstration. It is not derived from a real person or clinical chart.

## Contents

| Source type | Count | Purpose |
|---|---:|---|
| Synthetic clinical note | 1 | Seizure, syndrome, and reported comorbidity phrases |
| Synthetic EEG finding | 1 | Biomarker evidence |
| Synthetic MRI finding | 1 | Biomarker and structural etiology evidence |
| Synthetic medication record | 1 | Treatment-observation evidence |
| Synthetic patient diary | 1 | Corroborating seizure description |

## Direct identifiers

None. The fixture loader requires a `SYN-` case ID and rejects common direct-identifier keys such as name, date of birth, address, and MRN.

## Appropriate use

- Automated tests
- Public UI demonstration
- Reproducibility and provenance review
- Architecture discussion

## Inappropriate use

- Clinical research conclusions
- Model performance evaluation
- Epidemiology or prevalence estimates
- Training a medical model
- Representing the diversity of epilepsy presentations

## Versioning

The fixture has an explicit version. Changes to its content alter the source hash, ledger chain, run hash, profile hash, and final bundle hash.
