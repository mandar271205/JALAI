# JalRakshak AI — Deletion Candidates Audit Report

This report documents all files quarantined in `_to_review_delete/` during the repository simplification refactor. In accordance with the **ABSOLUTE NO-DELETE RULE**, no files were permanently deleted. Every item has been moved and cataloged with full forensic traceability.

---

## Quarantined Candidate Ledger

| Original Path | Quarantined Path | Category | Why It Was Moved | References Found | Replacement | Deletion Assessment | Action Required by Owner |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tmp.py` | `_to_review_delete/temp/tmp.py` | `TEMP` | Scratch IPython nbformat JSON reader left in repository root; unused by any production module. | `.gitignore` | None | `LIKELY_SAFE_TO_DELETE` | Inspect and confirm deletion. |
| `out.log` | `_to_review_delete/temp/out.log` | `TEMP` | 0-byte empty log file in root. | `.gitignore` | None | `LIKELY_SAFE_TO_DELETE` | Inspect and confirm deletion. |
| `src/jalrakshak_ml/flood/dataset_builder.py` | `_to_review_delete/legacy/flood/dataset_builder.py` | `LEGACY` | Defective Phase 10 dataset builder (broadcast single peak depth across 4 horizons). Quarantined and replaced with verified dataset. Rejection stub preserved. | `reports/phase11_reproducibility_manifest.md` | `src/jalrakshak_ml/flood/verified_dataset.py` | `DO_NOT_DELETE` | Preserve for historical reproducibility and audit compliance. |
| `notebooks/02_phase4e_deep_model_tournament.ipynb` | `_to_review_delete/temp/02_phase4e_deep_model_tournament.ipynb` | `SCRIPT` | Duplicate copy of canonical `colab/02_phase4e_deep_model_tournament.ipynb`. | `reports/phase4e_research_report.md` | `colab/02_phase4e_deep_model_tournament.ipynb` | `LIKELY_SAFE_TO_DELETE` | Compare with Colab notebook and approve deletion. |
| `models/flood_fno_smoke.pt` | *(Kept in `models/`)* | `MODEL` | CPU smoke-test checkpoint (loss 0.1704). Non-operational per scientific claim gates. | `reports/fno_smoke_evaluation.json`, `claim_gates.py` | None | `DO_NOT_DELETE` | Kept in place; do not delete research artifact. |
| `test.hdf5` | *(Kept in root / gitignored)* | `TEMP` | 8.1MB temporary HDF5 test output. | `.gitignore` | None | `LIKELY_SAFE_TO_DELETE` | Delete from local drive if disk space needed. |
| `test_dem_output.tif` | *(Kept in root / gitignored)* | `TEMP` | 1.1MB GeoTIFF test output. | `.gitignore` | None | `LIKELY_SAFE_TO_DELETE` | Delete from local drive if disk space needed. |
| `test_gfs.grib2` | *(Kept in root / gitignored)* | `TEMP` | 663KB GFS GRIB2 test output. | `.gitignore` | None | `LIKELY_SAFE_TO_DELETE` | Delete from local drive if disk space needed. |

---

## Verification & Recovery

To verify that no active runtime imports depend on `_to_review_delete/`:
```bash
python -c "
import os, subprocess
res = subprocess.check_output(['git', 'grep', '-l', '_to_review_delete', 'src/', 'backend/', 'tests/'], text=True)
print('Active code references:', res.strip() or 'None (Clean!)')
"
```

To restore any quarantined file back to its original location:
```bash
git mv _to_review_delete/<category>/<file> <original_path>
```
