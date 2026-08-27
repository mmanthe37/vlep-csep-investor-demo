# Contributing

This repository is currently an owner-led research prototype.

## Before opening a pull request

```bash
python -m unittest discover -s tests_mvp -v
python scripts/export_investor_demo.py
cd apps/investor-demo
npm ci
npm run typecheck
npm run build
```

Keep changes synthetic-only, deterministic, source-cited, and explicit about clinical limitations. New terminology mappings must include source and target releases, decision status, rationale, provenance, and tests.

Do not submit PHI, real patient records, secrets, unsupported clinical claims, or documentary metrics without their underlying reproducible evidence.
