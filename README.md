# JalRakshak AI — ML + Geospatial Starter

This repository is **Sprint 0 / foundation only**. It deliberately does **not**
jump to ConvLSTM, DGMR, SWMM/LISFLOOD or FNO yet.

The goal of this starter is to make the ML/GIS side reproducible and backend-ready:

1. freeze the ML-side contracts,
2. define one pilot grid,
3. ingest data through replaceable adapters,
4. standardize/QC it,
5. produce a canonical processed weather artifact,
6. prove the pipeline works end-to-end on a deterministic demo fixture.

## Pilot used in this starter

Working implementation choice: **Mumbai**.

- API CRS: `EPSG:4326`
- Internal analysis CRS: `EPSG:32643` (UTM zone 43N)
- Working WGS84 bbox: `[72.75, 18.85, 73.05, 19.30]`
- Canonical grid: `256 x 256`
- Initial temporal step: `10 minutes`

The bbox is a project implementation choice, not a claim from the PRD. We can
tighten/expand it after inspecting real data coverage.

## 1. One-time machine setup

Recommended on Windows/Linux/macOS: Miniconda/Micromamba/Conda with conda-forge,
because GDAL/Rasterio installation is much less painful there.

```bash
conda env create -f environment.yml
conda activate jalrakshak
pip install -e ".[dev]"
```

Optional but recommended:
- Git
- Docker Desktop / Docker Engine
- VS Code
- QGIS
- JupyterLab

GPU/CUDA is **not required for Sprint 0**.

## 2. Verify the environment

```bash
python scripts/check_env.py
```

## 3. Run the first end-to-end ML/GIS pipeline

```bash
python -m jalrakshak_ml.pipelines.bootstrap_demo
```

Expected outputs:

```text
data/raw/demo/synthetic_rainfall.nc
data/processed/demo/mumbai_rainfall.zarr/
data/processed/demo/latest_rainfall.tif
data/processed/demo/weatherframe_manifest.json
data/processed/demo/pilot_grid.json
```

This run proves:
- config loading works,
- a source adapter can produce data,
- timestamps/units/grid metadata exist,
- raster reprojection/resampling works,
- QC score is computed separately,
- canonical artifacts and manifest are generated.

## 4. Run tests

```bash
pytest -q
```

## 5. Folder ownership

```text
contracts/                  ML-owned internal contract + schemas
configs/                    pilot/data-source configuration
data/raw/                   immutable-ish downloaded/raw source files
data/interim/               parsed but not fully canonical
data/processed/             canonical arrays/rasters/manifests
src/jalrakshak_ml/adapters/ replaceable source-specific readers/downloaders
src/jalrakshak_ml/qc/       quality/freshness/range checks
src/jalrakshak_ml/preprocessing/ reprojection/resampling/grid logic
src/jalrakshak_ml/pipelines/ executable pipelines
src/jalrakshak_ml/nowcast/  later: persistence -> pySTEPS -> deep nowcast
src/jalrakshak_ml/fusion/   later: NWP + nowcast calibration/fusion
src/jalrakshak_ml/flood/    later: susceptibility -> physics -> FNO
src/jalrakshak_ml/risk/     later: H3 hazard/exposure/vulnerability
src/jalrakshak_ml/reports/  later: report verification
src/jalrakshak_ml/explain/  later: deterministic evidence + SHAP
src/jalrakshak_ml/serving/  later: /internal/v1 FastAPI service
```

## 6. What we do immediately after this starter runs

Do **not** train a deep model yet.

### Real data acquisition order

1. **Copernicus DEM GLO-30** — static terrain/elevation foundation.
2. **OpenStreetMap** — roads, waterways, critical assets and context.
3. **NASA GPM IMERG** — historical precipitation baseline/training-validation data.
4. **NOAA GFS/NOMADS** — open NWP development source.
5. **MOSDAC INSAT-3D/3DR** — satellite QPE/context when access is available.
6. **IMD DWR/AWS adapters** — keep interfaces ready; do not block the build on privileged access.

Every source gets its own adapter, and every adapter must ultimately emit data
that can be converted to the same canonical grid + metadata model.

## 7. Sprint 0 Definition of Done

- [ ] repository installs on your laptop
- [ ] `check_env.py` passes
- [ ] `bootstrap_demo` creates all 5 outputs
- [ ] tests pass
- [ ] `contracts/internal-ml-openapi.yaml` is committed
- [ ] `WeatherFrame` schema is committed
- [ ] Mumbai pilot grid is frozen for the first development cycle
- [ ] real-data acquisition checklist has started
- [ ] no model training has started yet

After that, the next code milestone is **real DEM + OSM + historical rainfall
adapters and the canonical data cube**, not ConvLSTM.

## Phase 3: ConvLSTM nowcasting

Phase 3 uses native 30-minute GPM timing and whole-event splits. The historical
acquisition command is read-only by default:

```bash
python scripts/acquire_phase3_data.py
python scripts/acquire_phase3_data.py --execute
```

The configured safety limits are in
`configs/training/convlstm_mumbai_v1.yaml`. Increase the event list and limits
deliberately; the current three 12-hour windows exercise the pipeline but are
not enough for a scientifically meaningful model validation.

Train locally only for CPU smoke testing:

```bash
python scripts/train_convlstm.py --device cpu
```

For real training, open `colab/01_convlstm_training.ipynb`, select a GPU
runtime, configure the repository/dataset/output paths, and run the cells in
order. The notebook supports optional repository clone/pull, Google Drive,
resume from `latest.pt`, held-out comparison against Persistence and pySTEPS,
and export of checkpoints, metrics, and plots.

Do not set `PHASE_3_MODEL_VALIDATED=true` for a CPU smoke run or for the legacy
23-frame Phase-2 replay. It requires genuine GPU training on an approved larger
historical corpus followed by held-out event evaluation.
