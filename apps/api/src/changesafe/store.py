"""Durable SQLite run state and ordered event storage."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiosqlite
from uuid6 import uuid7

from changesafe.domain import (
    AnalysisResult,
    ChangeRequest,
    EvidenceRef,
    PublicationReceipt,
    PublicError,
    RunEvent,
    RunState,
    RunView,
)


class InvalidTransition(ValueError):
    """Raised when a run attempts an illegal state transition."""


ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.LOADING_CONTEXT}),
    RunState.LOADING_CONTEXT: frozenset({RunState.SCORING_RISK, RunState.FAILED}),
    RunState.SCORING_RISK: frozenset({RunState.GENERATING, RunState.FAILED}),
    RunState.GENERATING: frozenset({RunState.VALIDATING, RunState.FAILED}),
    RunState.VALIDATING: frozenset({RunState.AWAITING_APPROVAL, RunState.FAILED}),
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
                    """
                )
                await connection.commit()
            self._initialized = True

    async def create(self, change: ChangeRequest) -> RunView:
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
            await connection.execute(
                """INSERT INTO runs(
                    run_id, state, request_json, analysis_json, publication_json,
                    error_json, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    str(run_id),
                    run.state.value,
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
            await connection.commit()
        return run

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
                error.model_dump_json() if error is not None else row["error_json"]
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
