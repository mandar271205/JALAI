from datetime import UTC, datetime
from typing import Any

from app.domains.responders.service import responder_service


class OfflineSyncEngine:
    """
    Offline batch synchronization engine with client_id idempotency
    and strict optimistic locking conflict detection.
    """

    def __init__(self):
        # Set of processed mutation IDs: mutation_id -> result
        self._processed_mutations: dict[str, dict[str, Any]] = {}

    def process_batch_sync(
        self,
        client_id: str,
        sync_version: int,
        client_timestamp: str,
        mutations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        results = []
        now = datetime.now(UTC).isoformat()

        for mut in mutations:
            mutation_id = mut.get("mutation_id")
            entity_type = mut.get("entity_type")
            action = mut.get("action")
            entity_id = mut.get("entity_id")
            base_version = mut.get("base_version", 1)
            data = mut.get("data", {})

            # 1. Idempotency check: duplicate mutation
            if mutation_id in self._processed_mutations:
                results.append(
                    {
                        "mutation_id": mutation_id,
                        "status": "duplicate",
                        "note": "Mutation already applied; skipped duplicate safely.",
                        "cached_result": self._processed_mutations[mutation_id],
                    }
                )
                continue

            # 2. Process RESPONDER_TASK mutation
            if entity_type == "RESPONDER_TASK":
                try:
                    task = responder_service.get_task(entity_id)
                    current_version = task["version"]

                    # Optimistic locking check: conflict detection
                    if base_version != current_version:
                        conflict_res = {
                            "mutation_id": mutation_id,
                            "entity_id": entity_id,
                            "status": "needs_merge",
                            "server_version": current_version,
                            "base_version": base_version,
                            "message": f"Conflict: Server task is at version {current_version}, client mutation was based on version {base_version}.",
                        }
                        results.append(conflict_res)
                        continue

                    # Apply mutation
                    updated_task = responder_service.apply_action(
                        task_id=entity_id,
                        action=action,
                        expected_version=base_version,
                        actor_id=client_id,
                        measured_depth_cm=data.get("depth_cm"),
                        evidence_url=data.get("evidence_url"),
                        notes=data.get("notes"),
                    )

                    success_res = {
                        "mutation_id": mutation_id,
                        "entity_id": entity_id,
                        "status": "accepted",
                        "new_version": updated_task["version"],
                        "applied_at": now,
                    }
                    self._processed_mutations[mutation_id] = success_res
                    results.append(success_res)

                except Exception as e:
                    results.append(
                        {"mutation_id": mutation_id, "status": "rejected", "error": str(e)}
                    )
            else:
                # Other generic entities
                accepted = {"mutation_id": mutation_id, "status": "accepted", "applied_at": now}
                self._processed_mutations[mutation_id] = accepted
                results.append(accepted)

        return {
            "client_id": client_id,
            "processed_count": len(results),
            "synced_at": now,
            "results": results,
        }


sync_engine = OfflineSyncEngine()
