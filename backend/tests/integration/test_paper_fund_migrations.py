"""Exercise Alembic upgrades, including the previously deployed paper schema.

Use HF_TEST_DATABASE_URL pointing to a disposable PostgreSQL database. Every
test creates and removes its own schema; no application's schema is touched.
Unlike the ORM integration fixtures, these tests never call create_all().
"""

import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

import httpx
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.auth import AuthenticatedUser, require_capital_user
from app.db.session import get_session
from app.main import app
from app.models import PaperEquitySnapshot, PaperFundRun, PaperOrder


TEST_URL = os.environ.get("HF_TEST_DATABASE_URL")
PRE_REPAIR_HEAD = "202610020002"
REPAIR_HEAD = "202610050002"
BACKEND = Path(__file__).resolve().parents[2]


def _upgrade(connection, target):
    """Run real Alembic revision steps and update the schema's version table."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    context = MigrationContext.configure(
        connection,
        opts={"fn": lambda heads, _: script._upgrade_revs(target, heads)},
    )
    with Operations.context(context):
        context.run_migrations()


@skipUnless(TEST_URL, "Set HF_TEST_DATABASE_URL to a disposable PostgreSQL database.")
class PaperFundMigrationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = f"hf_migration_{uuid4().hex}"
        self.engine = create_async_engine(
            TEST_URL,
            connect_args={"server_settings": {"search_path": self.schema}},
        )
        async with self.engine.begin() as connection:
            await connection.execute(CreateSchema(self.schema))
            await connection.run_sync(_upgrade, PRE_REPAIR_HEAD)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.owner = f"migration-test-{uuid4().hex}"

        async def dependency_session():
            async with self.factory() as session:
                yield session

        app.dependency_overrides[get_session] = dependency_session
        app.dependency_overrides[require_capital_user] = lambda: AuthenticatedUser(
            id=self.owner, email=None
        )

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        async with self.engine.begin() as connection:
            await connection.execute(DropSchema(self.schema, cascade=True))
        await self.engine.dispose()

    async def _repair(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(_upgrade, REPAIR_HEAD)
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            self.assertEqual(revision, REPAIR_HEAD)

    async def _assert_schema_matches_models(self):
        async with self.engine.connect() as connection:
            def verify(sync_connection):
                inspector = inspect(sync_connection)
                for model in (PaperFundRun, PaperOrder, PaperEquitySnapshot):
                    table = model.__table__
                    actual = {column["name"]: column for column in inspector.get_columns(table.name)}
                    self.assertEqual(set(actual), set(table.columns.keys()), table.name)
                    for column in table.columns:
                        self.assertEqual(actual[column.name]["nullable"], column.nullable, column.name)
                        self.assertEqual(
                            str(actual[column.name]["type"].compile(dialect=sync_connection.dialect)),
                            str(column.type.compile(dialect=sync_connection.dialect)),
                            column.name,
                        )
                    indexes = {index["name"]: index for index in inspector.get_indexes(table.name)}
                    self.assertEqual(set(indexes), {index.name for index in table.indexes}, table.name)
                    for index in table.indexes:
                        self.assertEqual(indexes[index.name]["column_names"], [c.name for c in index.columns])
                        self.assertEqual(indexes[index.name]["unique"], index.unique)
                    constraints = {c["name"] for c in inspector.get_check_constraints(table.name)}
                    required_checks = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
                    self.assertEqual(constraints, required_checks)
            await connection.run_sync(verify)

    async def _start_and_read(self, key):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {"starting_cash": "10000", "duration_days": 7}
            first = await client.post("/api/paper-fund/start", json=body, headers={"Idempotency-Key": key})
            self.assertEqual(first.status_code, 200, first.text)
            replay = await client.post("/api/paper-fund/start", json=body, headers={"Idempotency-Key": key})
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(first.json()["run"]["id"], replay.json()["run"]["id"])
            overview = await client.get("/api/paper-fund")
            self.assertEqual(overview.status_code, 200, overview.text)
            self.assertEqual(overview.json()["run"]["id"], first.json()["run"]["id"])
            self.assertEqual(Decimal(overview.json()["run"]["cash_balance"]), Decimal("10000"))
            self.assertEqual(overview.json()["orders"], [])
            return first.json()["run"]["id"]

    async def test_deployed_head_without_start_key_is_repaired_and_api_starts(self):
        # Reproduce the real failure: Alembic says head, but that already-applied
        # migration was later edited to add a field absent from this database.
        async with self.engine.begin() as connection:
            await connection.execute(text("ALTER TABLE paper_fund_runs DROP COLUMN start_key"))
            self.assertEqual(
                await connection.scalar(text("SELECT version_num FROM alembic_version")),
                PRE_REPAIR_HEAD,
            )
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/api/health/db")).status_code, 503)
        await self._repair()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/api/health/db")).status_code, 200)
        await self._assert_schema_matches_models()
        await self._start_and_read("repaired-start")

    async def test_current_schema_upgrade_preserves_run_and_start_replay(self):
        from app.services.paper_fund.engine import POLICY
        run_id = str(uuid4())
        now = datetime.now(timezone.utc)
        async with self.engine.begin() as connection:
            await connection.execute(text("""INSERT INTO paper_fund_runs
                (id, owner_user_id, start_key, status, starting_cash, cash_balance,
                 high_water_equity, max_drawdown_pct, started_at, ends_at, policy, blockers)
                VALUES (:id, :owner, 'before-repair', 'running', 10000, 10000,
                        10000, 0, :now, :ends, CAST(:policy AS JSONB), '[]'::jsonb)"""),
                {"id": run_id, "owner": self.owner, "now": now,
                 "ends": now + timedelta(days=7), "policy": json.dumps(POLICY)})
        await self._repair()
        await self._repair()
        await self._assert_schema_matches_models()
        self.assertEqual(await self._start_and_read("before-repair"), run_id)
        async with self.factory() as session:
            runs = list(await session.scalars(select(PaperFundRun)))
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].start_key, "before-repair")

    async def test_existing_column_with_missing_unique_index_is_repaired(self):
        async with self.engine.begin() as connection:
            await connection.execute(text("DROP INDEX uq_paper_fund_start_key"))
        await self._repair()
        await self._assert_schema_matches_models()
        await self._start_and_read("index-repaired")
