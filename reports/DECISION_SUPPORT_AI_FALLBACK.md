# JalRakshak AI — Model-First + Backend AI Fallback Architecture
## Rainfall & Flood Unified Inference Layer with Three-Model AI Orchestration

---

## 1. System Philosophy & Executive Summary

The JalRakshak AI Decision Support Inference Layer provides an authoritative, resilient, and scientifically honest serving layer for **both** precipitation nowcasting and urban flood risk.

The design strictly rejects the anti-pattern of "LLM vs. physical model voting." Instead, it enforces a deterministic hierarchy:
1. **Validated Numerical/Physics Model Evidence**: Primary and authoritative whenever available and permitted by scientific claim gates.
2. **Deterministic Environmental & Geospatial Evidence**: GFS synoptic NWP, GPM IMERG observations, DEM topographic elevation, slope, ESA WorldCover roughness, OSM drainage channels, and HxExV exposure-vulnerability metrics.
3. **Structured Auxiliary AI Inference**: Provider-agnostic LLMs that interpret genuine evidence into operational narratives, extract key risk drivers, and propose actionable civil defense measures.
4. **Selective Heavy Verification**: An independent reasoning layer that audits candidate assessments against original empirical evidence when conditions are severe, conflicting, or sensitive.

```
                    ┌───────────────────────────────────────┐
                    │ Request (Rainfall / Flood Location)   │
                    └───────────────────┬───────────────────┘
                                        │
                                        ▼
                           Check Numerical Model State
                                        │
                       ┌────────────────┴────────────────┐
                       │                                 │
                 MODEL AVAILABLE                  MODEL UNAVAILABLE
                       │                                 │
                       ▼                                 ▼
            Authoritative Numerical             Genuine Environmental
             Forecast / Simulation                     Evidence
           (PySTEPS / LISFLOOD / FNO)            (GFS / GPM / DEM / HxExV)
                       │                                 │
                       │                                 ▼
                       │                      Model 1: Groq GPT-OSS-120B
                       │                       [Failover: Nemotron Light]
                       │                                 │
                       └────────────────┬────────────────┘
                                        │
                                        ▼
                            Anti-Hallucination Gates
                                        │
                              Severe / Disagreement?
                                  /            \
                                YES             NO
                                 │               │
                                 ▼               │
                         Model 3: Nemotron Ultra │
                           (Heavy Verifier)      │
                                 │               │
                                 └───────┬───────┘
                                         ▼
                            Deterministic Arbitration
                                         │
                                         ▼
                           FINAL DOMAIN INTELLIGENCE
```

---

## 2. Source Modes & State Transitions

Every response emitted by the decision support service operates under an explicit, auditable internal source mode:

| Source Mode | Primary Model State | AI Role | Output Behavior |
| :--- | :--- | :--- | :--- |
| `NUMERICAL_MODEL` | Available | None / Disabled | Quantitative numerical time series or grid values preserved without alteration. |
| `MODEL_PLUS_AI` | Available | Operational Interpretation | Model outputs authoritative numbers; AI generates operational narrative and actions. |
| `PROVISIONAL_AI` | Unavailable | Provisional Assessment | Constrained evidence-based assessment; `depth_m = null`; intensity bounded by GFS/GPM. |
| `DETERMINISTIC_FALLBACK` | Unavailable | Failed / Offline | Rule-based baseline derived from empirical thresholds; no LLM claims. |
| `INSUFFICIENT_EVIDENCE` | Unavailable | N/A | Triggered when neither model nor valid meteorological observations exist. |

---

## 3. Three-Model AI Orchestration Architecture

The system utilizes three distinct model roles across two API providers:

### Model 1 — Primary Generator
- **Provider**: Groq Cloud
- **Model ID**: `openai/gpt-oss-120b`
- **Role**: `primary_generator`
- **Execution**: The first external AI model called for all standard requests.
- **Responsibilities**: Interprets numerical time-series, generates provisional forecasts from GFS/GPM, synthesizes flood risk from terrain and HxExV, and drafts actionable warnings.

### Model 2 — Fast Secondary / Failover
- **Provider**: NVIDIA NIM
- **Model ID**: `nvidia/nemotron-3.5-lightning-30b-a3b`
- **Role**: `secondary_generator`
- **Execution**: Invoked ONLY when Model 1 times out, returns HTTP 5xx, or outputs malformed JSON.
- **Responsibilities**: Mirror of Model 1 with identical Pydantic schema validation and anti-hallucination constraints.

### Model 3 — Heavy Verifier / Scientific Judge
- **Provider**: NVIDIA NIM
- **Model ID**: `nvidia/nemotron-3-ultra-550b-a55b`
- **Role**: `heavy_verifier`
- **Execution**: NOT invoked for routine low-risk requests. Triggered exclusively when:
  1. Rainfall severity is `HIGH` or `SEVERE`
  2. Flood risk is `HIGH` or `SEVERE`
  3. AI candidate materially disagrees with numerical model baseline
  4. Evidence sources conflict (e.g. GFS predicts heavy rain but persistence is zero)
  5. Candidate confidence is below threshold (`AI_VERIFIER_MIN_SUPPORT = 0.65`)
  6. Explicit audit/verification mode requested
- **Verifier Contract**: Emits a strict structured judgment (`ACCEPT`, `DOWNGRADE`, `REJECT`, or `INSUFFICIENT_EVIDENCE`). Does NOT rewrite physical numbers.

---

## 4. Anti-Hallucination Gates & Scientific Claim Integrity

To preserve scientific truthfulness, the arbitration layer enforces non-negotiable gates:

1. **Flood Depth Sanctity**:
   - If no genuine hydrodynamic solver output (LISFLOOD-FP / validated FNO checkpoint) exists in the input payload, `depth_m` is strictly enforced as `None`/`null`.
   - Any LLM attempt to fabricate numerical water depth (e.g. "0.6m", "1.2m") is rejected or sanitized to `null`.
2. **Rainfall Envelope Clamping**:
   - Generated intensity bands cannot exceed the maximum observed rate from GPM, GFS, or radar without physical justification. Any excess is clamped to the evidence upper bound.
3. **No LLM Majority Overrule**:
   - A vote of 2 LLMs cannot override a validated numerical model. The numerical model is always primary.
4. **Forbidden Fabrications**:
   - Candidate summaries and factors are audited against forbidden tokens (`observed_depth_gauge`, `insat_3d_direct_telemetry`, etc.) to prevent claiming unintegrated sensors.

---

## 5. Privacy, Security & Public UI Decoupling

- **Zero Provider Branding**: Public user-facing API responses present domain intelligence (Rainfall Forecast, Flood Risk, Horizon, Confidence, Factors, Actions) without revealing provider names (`groq`, `nvidia`, `nemotron`, `gpt`) or "LLM fallback".
- **Internal Audit Provenance**: Complete traceability is preserved in the internal `provenance` block (`source_mode`, `ai_generator_slot`, `ai_generator_provider`, `ai_verifier_verdict`, `evidence_ids`, `generated_at`).
- **Prompt Injection Defense**: Citizen reports and user-entered text are sanitized and serialized exclusively within payload data fields. They are never concatenated into system instruction prompts.
- **Zero Secrets in Repository**: No API keys are committed. Environment templates use `CHANGE_ME_...` placeholders.

---

## 6. How Future Frozen Winners & Physics Solvers Plug In

1. **Phase 4E Rainfall Tournament Winner**:
   - When the 12/3/3 tournament on Colab concludes and a winning checkpoint is frozen, serving code loads the model under `src/jalrakshak_ml/nowcast/`.
   - The inference layer automatically transitions from `PROVISIONAL_AI` to `MODEL_PLUS_AI` without altering frontend endpoints or API contracts.
2. **Validated LISFLOOD-FP / FloodFNO**:
   - When calibrated depth simulations or trained FNO surrogate models satisfy `ScientificClaimGates`, the genuine depth rasters populate `numerical_model_output["depth_m"]`.
   - `depth_m` automatically transitions from `null` to the genuine physical depth.
