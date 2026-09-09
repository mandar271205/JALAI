# final ml claim matrix

```json
{
  "claims": {
    "JalRakshak executes genuine LISFLOOD-FP.": "SUPPORTED",
    "Corrected LISFLOOD diagnostic exists.": "SUPPORTED",
    "Old Phase 10 six-scenario corpus is valid for FNO training.": "NOT_YET_SUPPORTED",
    "Corrected physics corpus is valid.": "SUPPORTED",
    "FloodFNO historical smoke training occurred.": "SUPPORTED",
    "FloodFNO is scientifically validated.": "NOT_YET_SUPPORTED",
    "FloodFNO is calibrated.": "NOT_YET_SUPPORTED",
    "FloodFNO is operational.": "NOT_YET_SUPPORTED",
    "Flood depth is calibrated to observed Mumbai truth.": "NOT_YET_SUPPORTED",
    "Risk decomposition is executable.": "SUPPORTED",
    "Rainfall final winner is frozen.": "NOT_YET_SUPPORTED",
    "Radar/INSAT are operationally populated.": "NOT_YET_SUPPORTED",
    "Citizen ML verifier exists.": "NOT_YET_SUPPORTED",
    "Runs genuine LISFLOOD-FP simulations": "SUPPORTED",
    "Solver-generated flood-depth arrays exist": "SUPPORTED",
    "Legacy solver arrays correctly located on Mumbai grid": "NOT_YET_SUPPORTED",
    "Exposure complete for Mumbai": "PARTIALLY_SUPPORTED",
    "Social vulnerability available": "NOT_YET_SUPPORTED",
    "Citizen flood reports verified by trained ML": "NOT_YET_SUPPORTED"
  },
  "gates": {
    "PHYSICS_DOMAIN_READY": true,
    "RAINFALL_FORCING_READY": true,
    "LISFLOOD_EXECUTABLE": true,
    "LISFLOOD_SMOKE_EXECUTED": true,
    "GENUINE_SOLVER_OUTPUT_AVAILABLE": true,
    "CORRECTED_SOLVER_OUTPUT_AVAILABLE": true,
    "CORRECTED_SOLVER_GRID_VALID": true,
    "OLD_PHASE10_TRAINING_TARGETS_VERIFIED": false,
    "PHYSICS_DATASET_READY": true,
    "FNO_READY_FOR_SMOKE": true,
    "FNO_ACTUALLY_TRAINED": true,
    "FNO_SCIENTIFICALLY_VALIDATED": false,
    "FNO_CALIBRATED": false,
    "FNO_OPERATIONAL": false,
    "EXPOSURE_READY": true,
    "VULNERABILITY_READY": true,
    "RISK_ENGINE_READY": true,
    "UNCERTAINTY_READY": true,
    "EXPLAINABILITY_READY": true,
    "CITIZEN_VERIFICATION_READY": true,
    "CITIZEN_ML_MODEL_AVAILABLE": false,
    "RAIN_FORECAST_WINNER_FROZEN": false
  },
  "blockers": [
    "Legacy corpus quarantined: grid distortion, forcing timing defects, repeated peak targets.",
    "Corrected corpus is only a small smoke corpus with one 60-minute target; expand events/time horizons before serious FNO training.",
    "Full Phase 4E Colab tournament and explicit winner freeze remain external.",
    "Observed flood-depth truth, calibrated hydraulics and social vulnerability missing.",
    "Population/buildings/power coverage incomplete; source dates do not establish historical exposure.",
    "No real labeled citizen corpus or calibrated uncertainty evidence."
  ]
}
```
