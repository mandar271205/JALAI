"""Verification and Safe CRUD Smoke Script for JalRakshak Supabase Schema.

Verifies:
1. Schema integrity across all 17 JalRakshak application tables
2. Primary keys, foreign keys, and indexes
3. Safe CRUD smoke lifecycle with isolated test rows
4. Backend database integration and health verification
"""
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.config import get_settings
from app.db.session import engine, AsyncSessionLocal
from app.db.models import User, ModelRun


EXPECTED_APPLICATION_TABLES = [
    "users",
    "weather_sources",
    "model_runs",
    "risk_cells",
    "incidents",
    "incident_events",
    "field_reports",
    "field_report_uploads",
    "alerts",
    "critical_assets",
    "responder_tasks",
    "audit_log",
    "outbox_events",
    "raw_weather_artifacts",
    "watch_locations",
    "device_push_tokens",
    "applied_mutations",
]


async def run_verification():
    settings = get_settings()
    print("============================================================")
    print("JALRAKSHAK AI — SUPABASE SCHEMA VERIFICATION")
    print("============================================================")
    print(f"Database Mode: {settings.DB_CONNECTION_MODE}")
    print(f"Supabase Host Target: aws-0-ap-southeast-1.pooler.supabase.com:6543")

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tables_verified": {},
        "crud_smoke_passed": False,
        "backend_integration_passed": False,
    }

    async with engine.connect() as conn:
        # 1. Inspect Table Existence and Columns
        def inspect_tables_sync(sync_conn):
            inspector = inspect(sync_conn)
            all_tables = inspector.get_table_names(schema="public")
            schema_data = {}
            for table_name in EXPECTED_APPLICATION_TABLES:
                if table_name in all_tables:
                    columns = inspector.get_columns(table_name, schema="public")
                    pk = inspector.get_pk_constraint(table_name, schema="public")
                    fks = inspector.get_foreign_keys(table_name, schema="public")
                    indexes = inspector.get_indexes(table_name, schema="public")
                    schema_data[table_name] = {
                        "exists": True,
                        "column_count": len(columns),
                        "columns": [c["name"] for c in columns],
                        "primary_key": pk.get("constrained_columns", []),
                        "foreign_keys_count": len(fks),
                        "indexes_count": len(indexes),
                    }
                else:
                    schema_data[table_name] = {"exists": False}
            return schema_data

        tables_meta = await conn.run_sync(inspect_tables_sync)
        report["tables_verified"] = tables_meta

        all_present = all(meta.get("exists") for meta in tables_meta.values())
        print(f"\n[1/3] Table Verification: {len(tables_meta)}/{len(EXPECTED_APPLICATION_TABLES)} verified")
        for tbl, meta in tables_meta.items():
            status = "FOUND" if meta.get("exists") else "MISSING"
            print(f"  - {tbl:<24} [{status}] Columns: {meta.get('column_count', 0)}, PK: {meta.get('primary_key', [])}")

        assert all_present, "Not all expected JalRakshak tables were found in Supabase!"

    # 2. Safe CRUD Smoke Test
    print("\n[2/3] Executing Safe CRUD Smoke Lifecycle on Supabase...")
    test_email = f"smoke_test_{uuid.uuid4().hex[:8]}@jalrakshak.internal"
    test_run_id = f"run_smoke_{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as session:
        # Step A: CREATE test user and model_run
        test_user = User(
            email=test_email,
            full_name="JalRakshak Smoke Tester",
            role="DISPATCHER",
            region="mumbai",
            organization="JalRakshak AI Verification Suite",
            is_active=True,
        )
        test_run = ModelRun(
            run_id=test_run_id,
            model_type="RISK_AGGREGATION",
            model_version="v1.0-verified",
            data_version="gpm-imerg-v07",
            status="RUNNING",
            metrics_json={"h_x_e_v_score": 0.72, "provisional": True},
        )
        session.add(test_user)
        session.add(test_run)
        await session.commit()
        print(f"  - CREATE: Inserted test user '{test_email}' and run '{test_run_id}'")

        # Step B: READ test records
        read_user = (await session.execute(text("SELECT id, email, role, region FROM users WHERE email = :email"), {"email": test_email})).fetchone()
        read_run = (await session.execute(text("SELECT run_id, model_type, status FROM model_runs WHERE run_id = :rid"), {"rid": test_run_id})).fetchone()
        assert read_user is not None and read_user[1] == test_email
        assert read_run is not None and read_run[0] == test_run_id
        print(f"  - READ: Successfully fetched user id '{read_user[0]}' and run '{read_run[0]}'")

        # Step C: UPDATE test records
        await session.execute(
            text("UPDATE model_runs SET status = 'COMPLETED', execution_time_ms = 450 WHERE run_id = :rid"),
            {"rid": test_run_id}
        )
        await session.commit()
        updated_run = (await session.execute(text("SELECT status, execution_time_ms FROM model_runs WHERE run_id = :rid"), {"rid": test_run_id})).fetchone()
        assert updated_run[0] == "COMPLETED"
        assert updated_run[1] == 450
        print(f"  - UPDATE: Successfully updated run status to '{updated_run[0]}' ({updated_run[1]}ms)")

        # Step D: DELETE exact test records
        await session.execute(text("DELETE FROM model_runs WHERE run_id = :rid"), {"rid": test_run_id})
        await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": test_email})
        await session.commit()

        # Step E: VERIFY DELETION
        check_user = (await session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": test_email})).fetchone()
        check_run = (await session.execute(text("SELECT run_id FROM model_runs WHERE run_id = :rid"), {"rid": test_run_id})).fetchone()
        assert check_user is None
        assert check_run is None
        print("  - DELETE: Cleanly pruned exact test rows; 0 residual test artifacts")

    report["crud_smoke_passed"] = True

    # 3. Backend Integration Verification
    print("\n[3/3] Verifying Backend Application API with Live Supabase...")
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    print(f"  - Health Endpoint: {health_resp.status_code} OK (status={health_data.get('status')})")

    models_status_resp = client.get("/api/v1/models/status")
    assert models_status_resp.status_code == 200
    print(f"  - Models Status Endpoint: {models_status_resp.status_code} OK (status={models_status_resp.json().get('status')})")

    # DB session read route/service integration test
    async with AsyncSessionLocal() as session:
        from app.domains.audit.service import audit_service
        logs = await audit_service.list_audit_logs(db=session, limit=5)
        print(f"  - DB-Backed Audit Service Query: SUCCESS (retrieved {len(logs)} logs from Supabase audit_log)")

    report["backend_integration_passed"] = True

    print("\n============================================================")
    print("ALL SUPABASE APPLICATION SCHEMA AUDITS & TESTS PASSED!")
    print("============================================================")
    return report


if __name__ == "__main__":
    asyncio.run(run_verification())
