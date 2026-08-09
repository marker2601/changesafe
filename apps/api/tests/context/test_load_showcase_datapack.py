from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from scripts.load_showcase_datapack import (
    LoadOptions,
    OfficialRuntime,
    load_showcase_datapack,
)


@dataclass(frozen=True)
class FakePack:
    name: str = "showcase-ecommerce"
    reference_timestamp: int = 1_700_000_000_000


@dataclass(frozen=True)
class FakeEntry:
    path: Path
    wait_for_completion: bool = False


class FakeClientConfig:
    def model_dump(self, **_kwargs: object) -> dict[str, object]:
        return {
            "server": "http://datahub.example",
            "token": "never-print-this-token",
        }


def make_runtime(
    tmp_path: Path,
    events: list[tuple[Any, ...]],
    *,
    fail_on: str | None = None,
) -> OfficialRuntime:
    entries = [
        FakeEntry(tmp_path / "01-foundation.json"),
        FakeEntry(tmp_path / "02-lineage.json", wait_for_completion=True),
    ]
    for entry in entries:
        entry.path.write_text("[]", encoding="utf-8")

    def get_pack(name: str, *, no_cache: bool) -> FakePack:
        events.append(("get_pack", name, no_cache))
        return FakePack()

    def download_pack(pack: FakePack, *, no_cache: bool) -> list[FakeEntry]:
        events.append(("download", pack.name, no_cache))
        return entries

    def apply_schema_filter(pack_path: Path, *, client_config: object) -> Path:
        assert isinstance(client_config, FakeClientConfig)
        events.append(("schema", pack_path.name))
        return pack_path

    def check_referential_integrity(pack_path: Path, *, client_config: object) -> None:
        assert isinstance(client_config, FakeClientConfig)
        events.append(("integrity", pack_path.name))

    def time_shift_file(
        *,
        input_path: Path,
        reference_timestamp: int,
        target_timestamp: int | None,
    ) -> Path:
        events.append(
            (
                "time_shift",
                input_path.name,
                reference_timestamp,
                target_timestamp,
            )
        )
        return input_path

    class FakePipeline:
        def __init__(self, config: dict[str, Any]) -> None:
            self.config = config
            self.filename = Path(config["source"]["config"]["path"]).name

        def run(self) -> None:
            events.append(("run", self.filename))

        def raise_from_status(self) -> None:
            events.append(("status", self.filename))
            if self.filename == fail_on:
                raise RuntimeError("pipeline failed with never-print-this-token")

    def pipeline_create(config: dict[str, Any]) -> FakePipeline:
        filename = Path(config["source"]["config"]["path"]).name
        events.append(("create", filename, config))
        return FakePipeline(config)

    return OfficialRuntime(
        get_pack=get_pack,
        check_trust=lambda pack: events.append(("trust", pack.name)),
        check_version_compatibility=lambda pack: events.append(("version", pack.name)),
        download_pack=download_pack,
        load_client_config=lambda: events.append(("config",)) or FakeClientConfig(),
        apply_schema_filter=apply_schema_filter,
        check_referential_integrity=check_referential_integrity,
        time_shift_file=time_shift_file,
        generate_run_id=lambda name: f"datapack-{name}-run",
        pipeline_create=pipeline_create,
        save_load_record=lambda pack, run_id: events.append(
            ("save", pack.name, run_id)
        ),
    )


def test_default_preview_performs_no_network_cache_or_datahub_mutation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("preview invoked a mutating or network operation")

    runtime = OfficialRuntime(
        get_pack=forbidden,
        check_trust=forbidden,
        check_version_compatibility=forbidden,
        download_pack=forbidden,
        load_client_config=forbidden,
        apply_schema_filter=forbidden,
        check_referential_integrity=forbidden,
        time_shift_file=forbidden,
        generate_run_id=forbidden,
        pipeline_create=forbidden,
        save_load_record=forbidden,
    )

    result = load_showcase_datapack(LoadOptions(), runtime=runtime)

    output = capsys.readouterr().out
    assert result.applied is False
    assert "PREVIEW ONLY" in output
    assert "--apply" in output
    assert "no network" in output.lower()
    assert "no datahub writes" in output.lower()


def test_apply_preserves_official_order_and_uses_only_restli_sync(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[tuple[Any, ...]] = []
    runtime = make_runtime(tmp_path, events)

    result = load_showcase_datapack(
        LoadOptions(apply=True, no_time_shift=False), runtime=runtime
    )

    creates = [event for event in events if event[0] == "create"]
    assert [event[1] for event in creates] == [
        "01-foundation.json",
        "02-lineage.json",
    ]
    for _, _, config in creates:
        assert config["sink"]["type"] == "datahub-rest"
        assert config["sink"]["config"]["endpoint"] == "restli"
        assert config["sink"]["config"]["mode"] == "sync"
        assert "async_wait" not in repr(config).lower()

    assert events.index(("status", "01-foundation.json")) < events.index(
        ("create", "02-lineage.json", creates[1][2])
    )
    assert [event for event in events if event[0] == "integrity"] == [
        ("integrity", "02-lineage.json")
    ]
    assert [event[1] for event in events if event[0] == "time_shift"] == [
        "01-foundation.json",
        "02-lineage.json",
    ]
    assert events[-1] == (
        "save",
        "showcase-ecommerce",
        "datapack-showcase-ecommerce-run",
    )
    assert result.applied is True
    assert result.file_count == 2
    assert "never-print-this-token" not in capsys.readouterr().out


def test_failed_ordered_part_never_saves_a_completed_load_record(
    tmp_path: Path,
) -> None:
    events: list[tuple[Any, ...]] = []
    runtime = make_runtime(tmp_path, events, fail_on="02-lineage.json")

    with pytest.raises(RuntimeError, match="pipeline failed"):
        load_showcase_datapack(LoadOptions(apply=True), runtime=runtime)

    assert not any(event[0] == "save" for event in events)
    assert ("status", "01-foundation.json") in events
    assert ("status", "02-lineage.json") in events


def test_no_time_shift_skips_official_time_shift(
    tmp_path: Path,
) -> None:
    events: list[tuple[Any, ...]] = []
    runtime = make_runtime(tmp_path, events)

    load_showcase_datapack(LoadOptions(apply=True, no_time_shift=True), runtime=runtime)

    assert not any(event[0] == "time_shift" for event in events)
