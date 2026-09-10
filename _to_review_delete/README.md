# JalRakshak AI — Deletion Candidates Quarantine (_to_review_delete/)

> [!CAUTION]
> **ABSOLUTE NO-DELETE POLICY**
> Files in this directory are **quarantined candidates for later manual review by the repository owner**.
> They must **NOT** be automatically purged, deleted, or removed by scripts or CI/CD pipelines.

---

## Purpose

To ensure zero accidental data loss while simplifying the repository tree for Web and Mobile integration, candidate files (scratch scripts, duplicate notebooks, empty logs, legacy defect implementations) have been safely moved here.

The repository owner will:
1. Review the contents of this folder and the entries in 
eview_manifest.json.
2. Inspect individual files and their documented replacements.
3. Explicitly approve or reject any permanent deletion.

---

## Directory Structure

`
_to_review_delete/
  ├── README.md               # This document
  ├── review_manifest.json    # Machine-readable candidate ledger
  ├── llm/                    # Legacy/experimental LLM files or prompts
  ├── models/                 # Model checkpoints marked non-operational
  ├── backend/                # Stale backend code / scratch files
  ├── ml/                     # ML modules superseded by consolidated packages
  ├── scripts/                # Obsolete one-off experiment scripts
  ├── reports/                # Intermediate or redundant report drafts
  ├── configs/                # Deprecated or duplicate configuration files
  ├── legacy/                 # Historical scientific code preserved for forensics
  │   └── flood/              # Defective Phase 10 dataset builder
  ├── temp/                   # Temporary test files, scratch scripts, notebooks
  └── misc/                   # Miscellaneous unclassified candidates
`

---

## Current Quarantined Candidates

| Original Path | Quarantined Path | Category | Reason | Replacement | Safety Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 	mp.py | _to_review_delete/temp/tmp.py | TEMP | Scratch IPython reader utility left in root. | None | LIKELY |
| out.log | _to_review_delete/temp/out.log | TEMP | 0-byte debug log file in root. | None | LIKELY |
| src/jalrakshak_ml/flood/dataset_builder.py | _to_review_delete/legacy/flood/dataset_builder.py | LEGACY | Defective Phase 10 dataset builder (quarantined). | src/jalrakshak_ml/flood/verified_dataset.py | DO_NOT_DELETE |
| 
otebooks/02_phase4e_deep_model_tournament.ipynb | _to_review_delete/temp/02_phase4e_deep_model_tournament.ipynb | SCRIPT | Duplicate of authoritative Colab notebook. | colab/02_phase4e_deep_model_tournament.ipynb | LIKELY |
| models/flood_fno_smoke.pt | *(Kept in models/)* | MODEL | Unvalidated CPU smoke checkpoint; non-operational. | None | DO_NOT_DELETE |
| 	est.hdf5 | *(Kept in root / gitignored)* | TEMP | 8.1MB temporary HDF5 test output. | None | LIKELY |

---

## Reverting a Move

If any file quarantined here is needed back in its original location, move it back using:
`ash
git mv _to_review_delete/<category>/<filename> <original_path>
`
All entries are preserved with original relative paths and Git commit context in 
eview_manifest.json.
