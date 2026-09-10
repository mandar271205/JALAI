# JalRakshak AI — Machine Learning & Scientific Physics Architecture (`ml/`)

> [!IMPORTANT]
> **Scientific Integrity & Claim Gates**
> The JalRakshak ML stack strictly maintains claim gates and separation between:
> 1. Validated numerical models (PySTEPS, operational ConvLSTM V3).
> 2. Hydrodynamic physical simulations (LISFLOOD-FP 8.0.3).
> 3. Neural operator surrogates (FloodFNO).
> 4. Deterministic geospatial risk baselines ($H \times E \times V$).
> 5. Backend LLM decision-support fallbacks (Groq GPT-OSS-120B + NVIDIA Nemotron 30B/550B).
>
> In accordance with repository architecture rules, canonical Python package code resides in `src/jalrakshak_ml/` to preserve import stability across all 34+ test suites and 80+ research scripts.

---

## Domain Architecture Map

```
ml/ (and src/jalrakshak_ml/)
├── rainfall/ (deep_nowcast/ & nowcast/)
│   ├── persistence.py             # Deterministic persistence baseline
│   ├── pysteps_adapter.py         # PySTEPS Lucas-Kanade optical flow
│   ├── convlstm_v3.py             # ConvLSTM V3 architecture
│   ├── unet_convgru.py            # U-Net + ConvGRU spatiotemporal architecture
│   ├── st_attention.py            # Spatial-temporal attention architecture
│   └── evaluation/                # Critical Success Index (CSI), ETS, Brier score
│
├── flood/ (flood/)
│   ├── lisflood_adapter.py        # LISFLOOD-FP 8.0.3 execution wrapper (fails closed)
│   ├── gpm_to_forcing.py          # Spatial interpolation of GPM IMERG to hydrodynamic grid
│   ├── domain.py                  # Mumbai catchment terrain, Manning's roughness, boundary
│   ├── fno.py                     # Fourier Neural Operator (FNO-2D) surrogate
│   ├── verified_dataset.py        # Corrected physics dataset loader (supersedes legacy)
│   └── susceptibility.py          # Topographic wetness and slope flood susceptibility
│
├── risk/ (risk/ & citizen/)
│   ├── exposure.py                # Infrastructure, population, and road exposure
│   ├── vulnerability.py           # Socioeconomic and elevation vulnerability
│   ├── intelligence.py            # Dynamic H x E x V risk scoring engine
│   ├── uncertainty.py             # Confidence calibration and variance bounds
│   └── citizen/                   # Multimodal report corroboration (heuristic verification)
│
├── geospatial/ (preprocessing/ & pipelines/)
│   ├── dem_pipeline.py            # SRTM / CartoDEM processing and slope generation
│   ├── osm_pipeline.py            # Overpass API extraction for roads, hospitals, schools
│   └── terrain.py                 # Flow accumulation, aspect, and hydrological conditioning
│
├── decision_support/ (decision_support/)
│   ├── schemas.py                 # Pydantic input/output contracts
│   ├── provider_router.py         # 3-Model router with SHA-256 caching and failover
│   ├── groq_provider.py           # Model 1: Groq openai/gpt-oss-120b (Primary Generator)
│   ├── nvidia_provider.py         # Model 2: Nemotron 30B (Failover) & Model 3: 550B (Verifier)
│   ├── rainfall_inference.py      # Model-first vs. Provisional AI rainfall pipeline
│   ├── flood_inference.py         # Model-first vs. Provisional AI flood pipeline
│   ├── arbitration.py             # Deterministic rules & anti-hallucination gates
│   └── provenance.py              # Cryptographic audit provenance generator
│
└── serving/ (serving/)
    ├── app.py                     # FastAPI application router
    └── service.py                 # Service boundaries for nowcast, inundation, risk, and decision-support
```

---

## Operating Modes

| Mode | Trigger Condition | Primary Source | Role of AI | Public Output |
| :--- | :--- | :--- | :--- | :--- |
| `NUMERICAL_MODEL` | Operational model available; AI disabled | PySTEPS / ConvLSTM V3 | None | Quantitative forecast |
| `MODEL_PLUS_AI` | Operational model available; AI enabled | Numerical Model | Qualitative interpretation & risk narrative | Quantitative numbers preserved + AI advice |
| `PROVISIONAL_AI` | Model training paused or unavailable | GFS / GPM / DEM / Susceptibility | Synthesizes provisional assessment bounded by evidence | Categorical risk & intensity band (`depth_m=None`) |
| `DETERMINISTIC_FALLBACK` | Model unavailable; AI unavailable or times out | Rules-based heuristics ($H \times E \times V$) | None | Heuristic baseline |
| `INSUFFICIENT_EVIDENCE` | Data quality < 0.20 or missing observations | None | Returns warning | Fails safe with diagnostic warning |
