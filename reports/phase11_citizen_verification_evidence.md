# phase11 citizen verification evidence

```json
{
  "version": "phase11_citizen_metadata_rules_v1",
  "status": "RULES_IMPLEMENTED_REAL_REPORTS_UNAVAILABLE",
  "CITIZEN_VERIFICATION_RULE_BASED": true,
  "CITIZEN_ML_MODEL_AVAILABLE": false,
  "real_report_accuracy_benchmark": null,
  "manual_review_required": true,
  "interface": "citizen.metadata_verifier.ReportVerifier",
  "rules": [
    "explicit-clock timestamp",
    "Mumbai bounds",
    "same-event spatial/time clustering",
    "text/media-hash duplicates",
    "rain/hazard consistency",
    "media type"
  ],
  "source_history_available": false
}
```
