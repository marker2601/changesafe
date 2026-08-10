"""Durable SQLite run state and ordered event storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from uuid import UUID

import aiosqlite
from uuid6 import uuid7

from changesafe.demo import DEMO_DATA_PRODUCT
from changesafe.domain import (
    AnalysisResult,
    ChangeRequest,
    EvidenceRef,
    LlmUsage,
    PublicationLedgerEntry,
    PublicationReceipt,
    PublicError,
    ReviewActivity,
    RunEvent,
    RunState,
    RunView,
)


class InvalidTransition(ValueError):
    """Raised when a run attempts an illegal state transition."""


class LlmBudgetExceeded(RuntimeError):
    """Raised before a run starts when its reserved LLM cost exceeds budget."""


MICRO_USD = Decimal(1_000_000)


def _usd_to_micros(value: Decimal) -> int:
    return int((value * MICRO_USD).to_integral_value(rounding=ROUND_CEILING))


ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.LOADING_CONTEXT}),
    RunState.LOADING_CONTEXT: frozenset(
        {
            RunState.SCORING_RISK,
            RunState.CONTEXT_FALLBACK_REQUIRED,
            RunState.FAILED,
        }
    ),
    RunState.CONTEXT_FALLBACK_REQUIRED: frozenset({RunState.LOADING_CONTEXT}),
    RunState.SCORING_RISK: frozenset({RunState.GENERATING, RunState.FAILED}),
    RunState.GENERATING: frozenset({RunState.VALIDATING, RunState.FAILED}),
    RunState.VALIDATING: frozenset(
        {
            RunState.VALIDATING_WAREHOUSE,
            RunState.AWAITING_APPROVAL,
            RunState.FAILED,
        }
    ),
    RunState.VALIDATING_WAREHOUSE: frozenset(
        {RunState.AWAITING_APPROVAL, RunState.FAILED}
    ),
    RunState.AWAITING_APPROVAL: frozenset(
        {RunState.PREPARING_PREVIEW, RunState.PUBLISHING, RunState.FAILED}
    ),
    RunState.PREPARING_PREVIEW: frozenset(
        {RunState.COMPLETED, RunState.PUBLICATION_FAILED}
    ),
    RunState.PUBLISHING: frozenset({RunState.COMPLETED, RunState.PUBLICATION_FAILED}),
    RunState.PUBLICATION_FAILED: frozenset(
        {RunState.PREPARING_PREVIEW, RunState.PUBLISHING}
    ),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunStore:
    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            self.database.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.database) as connection:
                await connection.executescript(
                    """
                    PRAGMA journal_mode = WAL;
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        session_id TEXT,
                        request_json TEXT NOT NULL,
                        analysis_json TEXT,
                        publication_json TEXT,
                        error_json TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS run_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        public_message TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, sequence),
                        FOREIGN KEY (run_id) REFERENCES runs(run_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_run_events_cursor
                        ON run_events(run_id, sequence);
                    CREATE TABLE IF NOT EXISTS publication_ledger (
                        idempotency_key TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        artifact_hash TEXT NOT NULL,
                        receipt_json TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (run_id) REFERENCES runs(run_id)
                    );
                    CREATE TABLE IF NOT EXISTS llm_usage (
                        run_id TEXT PRIMARY KEY,
                        reserved_microusd INTEGER NOT NULL,
                        actual_microusd INTEGER,
                        usage_json TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (run_id) REFERENCES runs(run_id)
                    );
                    """
                )
                columns_cursor = await connection.execute("PRAGMA table_info(runs)")
                columns = {
                    str(row[1]) for row in await columns_cursor.fetchall()
                }
                if "session_id" not in columns:
                    await connection.execute(
                        "ALTER TABLE runs ADD COLUMN session_id TEXT"
                    )
                await connection.commit()
            self._initialized = True

    async def create(
        self,
        change: ChangeRequest,
        *,
        session_id: str | None = None,
        llm_reservation_usd: Decimal = Decimal(0),
        llm_budget_usd: Decimal | None = None,
    ) -> RunView:
        await self.initialize()
        run_id = uuid7()
        now = _utc_now()
        run = RunView(
            run_id=run_id,
            state=RunState.CREATED,
            request=change,
            created_at=now,
            updated_at=now,
        )
        async with aiosqlite.connect(self.database) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            reservation_micros = _usd_to_micros(llm_reservation_usd)
            if reservation_micros:
                budget_cursor = await connection.execute(
                    """SELECT COALESCE(
                        SUM(COALESCE(actual_microusd, reserved_microusd)), 0
                    ) FROM llm_usage"""
                )
                budget_row = await budget_cursor.fetchone()
                committed_micros = int(budget_row[0]) if budget_row else 0
                if (
                    llm_budget_usd is not None
                    and committed_micros + reservation_micros
                    > _usd_to_micros(llm_budget_usd)
                ):
                    await connection.rollback()
                    raise LlmBudgetExceeded(
                        "The configured project LLM budget is exhausted."
                    )
            await connection.execute(
                """INSERT INTO runs(
                    run_id, state, session_id, request_json, analysis_json,
                    publication_json, error_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    str(run_id),
                    run.state.value,
                    session_id,
                    change.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            await connection.execute(
                """INSERT INTO run_events(
                    run_id, sequence, state, public_message, evidence_json, created_at
                ) VALUES (?, 1, ?, ?, '[]', ?)""",
                (str(run_id), run.state.value, "Run created", now.isoformat()),
            )
            if reservation_micros:
                await connection.execute(
                    """INSERT INTO llm_usage(
                        run_id, reserved_microusd, actual_microusd, usage_json,
                        created_at, updated_at
                    ) VALUES (?, ?, NULL, NULL, ?, ?)""",
                    (
                        str(run_id),
                        reservation_micros,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            await connection.commit()
        return run

    async def recent_activity(self, *, limit: int = 20) -> list[ReviewActivity]:
        await self.initialize()
        bounded_limit = max(1, min(limit, 50))
        async with aiosqlite.connect(self.database) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """SELECT run_id, state, session_id, analysis_json,
                    publication_json, created_at, updated_at
                    FROM runs ORDER BY created_at DESC LIMIT ?""",
                (bounded_limit,),
            )
            rows = await cursor.fetchall()

        activity: list[ReviewActivity] = []
        for row in rows:
            session_id = row["session_id"]
            session_label = (
                f"session-{hashlib.sha256(str(session_id).encode()).hexdigest()[:8]}"
                if session_id is not None
                else "session-unassigned"
            )
            analysis = (
                json.loads(str(row["analysis_json"]))
                if row["analysis_json"] is not None
                else None
            )
            publication = (
                json.loads(str(row["publication_json"]))
                if row["publication_json"] is not None
                else None
            )
            context_mode = (
                analysis.get("context", {}).get("provenance", {}).get("mode")
                if isinstance(analysis, dict)
                else None
            )
            publication_mode = (
                publication.get("mode")
                if isinstance(publication, dict)
                else None
            )
            activity.append(
                ReviewActivity(
                    run_id=row["run_id"],
                    session_label=session_label,
                    scenario=DEMO_DATA_PRODUCT,
                    state=row["state"],
                    context_mode=context_mode,
                    publication_mode=publication_mode,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return activity

    async def record_llm_usage(
        self, run_id: UUID | str, usage: LlmUsage
    ) -> None:
        await self.initialize()
        now = _utc_now().isoformat()
        actual_micros = _usd_to_micros(usage.estimated_cost_usd)
        async with aiosqlite.connect(self.database) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """UPDATE llm_usage SET actual_microusd = ?, usage_json = ?,
                    updated_at = ? WHERE run_id = ?""",
                (actual_micros, usage.model_dump_json(), now, str(run_id)),
            )
            if cursor.rowcount == 0:
                await connection.execute(
                    """INSERT INTO llm_usage(
                        run_id, reserved_microusd, actual_microusd, usage_json,
                        created_at, updated_at
                    ) VALUES (?, 0, ?, ?, ?, ?)""",
                    (
                        str(run_id),
                        actual_micros,
                        usage.model_dump_json(),
                        now,
                        now,
                    ),
                )
            await connection.commit()

    async def release_llm_reservation(self, run_id: UUID | str) -> None:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            await connection.execute(
                """UPDATE llm_usage SET actual_microusd = 0, updated_at = ?
                    WHERE run_id = ? AND actual_microusd IS NULL""",
                (_utc_now().isoformat(), str(run_id)),
            )
            await connection.commit()

    async def get_llm_usage(self, run_id: UUID | str) -> LlmUsage | None:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            cursor = await connection.execute(
                "SELECT usage_json FROM llm_usage WHERE run_id = ?",
                (str(run_id),),
            )
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return LlmUsage.model_validate_json(str(row[0]))

    async def llm_committed_cost_usd(self) -> Decimal:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            cursor = await connection.execute(
                """SELECT COALESCE(
                    SUM(COALESCE(actual_microusd, reserved_microusd)), 0
                ) FROM llm_usage"""
            )
            row = await cursor.fetchone()
        micros = int(row[0]) if row else 0
        return Decimal(micros) / MICRO_USD

    async def get(self, run_id: UUID | str) -> RunView | None:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (str(run_id),)
            )
            row = await cursor.fetchone()
        return self._run_from_row(row) if row is not None else None

    async def transition(
        self,
        run_id: UUID | str,
        state: RunState,
        *,
        public_message: str = "",
        evidence: list[EvidenceRef] | None = None,
        analysis: AnalysisResult | None = None,
        publication: PublicationReceipt | None = None,
        error: PublicError | None = None,
        clear_error: bool = False,
    ) -> RunView:
        await self.initialize()
        now = _utc_now()
        async with aiosqlite.connect(self.database) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (str(run_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                await connection.rollback()
                raise KeyError(str(run_id))
            current = RunState(str(row["state"]))
            if state not in ALLOWED_TRANSITIONS[current]:
                await connection.rollback()
                raise InvalidTransition(
                    f"invalid run transition: {current.value} -> {state.value}"
                )

            analysis_json = (
                analysis.model_dump_json()
                if analysis is not None
                else row["analysis_json"]
            )
            publication_json = (
                publication.model_dump_json()
                if publication is not None
                else row["publication_json"]
            )
            error_json = (
                None
                if state is RunState.COMPLETED or clear_error
                else error.model_dump_json()
                if error is not None
                else row["error_json"]
            )
            await connection.execute(
                """UPDATE runs SET state = ?, analysis_json = ?,
                    publication_json = ?, error_json = ?, updated_at = ?
                    WHERE run_id = ?""",
                (
                    state.value,
                    analysis_json,
                    publication_json,
                    error_json,
                    now.isoformat(),
                    str(run_id),
                ),
            )
            sequence_cursor = await connection.execute(
                """SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM run_events WHERE run_id = ?""",
                (str(run_id),),
            )
            sequence_row = await sequence_cursor.fetchone()
            if sequence_row is None:  # pragma: no cover - aggregate always returns
                await connection.rollback()
                raise RuntimeError("Could not allocate event sequence")
            sequence = int(sequence_row[0])
            await connection.execute(
                """INSERT INTO run_events(
                    run_id, sequence, state, public_message, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(run_id),
                    sequence,
                    state.value,
                    public_message or state.value.replace("_", " ").title(),
                    json.dumps(
                        [item.model_dump(mode="json") for item in evidence or []],
                        separators=(",", ":"),
                    ),
                    now.isoformat(),
                ),
            )
            await connection.commit()
        updated = await self.get(run_id)
        if updated is None:  # pragma: no cover - protected by transaction
            raise KeyError(str(run_id))
        return updated

    async def events(
        self, run_id: UUID | str, *, after_sequence: int = 0
    ) -> list[RunEvent]:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """SELECT * FROM run_events
                    WHERE run_id = ? AND sequence > ? ORDER BY sequence""",
                (str(run_id), after_sequence),
            )
            rows = await cursor.fetchall()
        return [
            RunEvent(
                run_id=UUID(str(row["run_id"])),
                sequence=int(row["sequence"]),
                state=RunState(str(row["state"])),
                public_message=str(row["public_message"]),
                evidence=json.loads(str(row["evidence_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def get_publication(
        self, idempotency_key: str
    ) -> PublicationLedgerEntry | None:
        await self.initialize()
        async with aiosqlite.connect(self.database) as connection:
            cursor = await connection.execute(
                """SELECT receipt_json FROM publication_ledger
                    WHERE idempotency_key = ?""",
                (idempotency_key,),
            )
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return PublicationLedgerEntry.model_validate_json(str(row[0]))

    async def save_publication(
        self, entry: PublicationLedgerEntry
    ) -> PublicationLedgerEntry:
        await self.initialize()
        now = _utc_now()
        updated = entry.model_copy(update={"updated_at": now})
        async with aiosqlite.connect(self.database) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """SELECT artifact_hash FROM publication_ledger
                    WHERE idempotency_key = ?""",
                (entry.idempotency_key,),
            )
            existing = await cursor.fetchone()
            if existing is not None and str(existing[0]) != entry.artifact_hash:
                await connection.rollback()
                raise ValueError("idempotency key is bound to another artifact hash")
            await connection.execute(
                """INSERT INTO publication_ledger(
                    idempotency_key, run_id, artifact_hash, receipt_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    receipt_json = excluded.receipt_json,
                    updated_at = excluded.updated_at""",
                (
                    updated.idempotency_key,
                    str(updated.run_id),
                    updated.artifact_hash,
                    updated.model_dump_json(),
                    updated.created_at.isoformat(),
                    updated.updated_at.isoformat(),
                ),
            )
            await connection.commit()
        return updated

    @staticmethod
    def _run_from_row(row: aiosqlite.Row) -> RunView:
        def decoded(name: str) -> object | None:
            value = row[name]
            return json.loads(str(value)) if value is not None else None

        return RunView.model_validate(
            {
                "run_id": row["run_id"],
                "state": row["state"],
                "request": decoded("request_json"),
                "analysis": decoded("analysis_json"),
                "publication": decoded("publication_json"),
                "error": decoded("error_json"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
