from __future__ import annotations

import json
import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

from apexos_in_season.source_probe import (
    deterministic_frame_digest,
    probe_sources,
    write_manifest,
)


NOW = datetime(2026, 9, 25, 18, 30, tzinfo=timezone.utc)


class FakePolarsFrame:
    def __init__(self, rows, columns=None):
        self._rows = list(rows)
        self.columns = list(columns or (self._rows[0].keys() if self._rows else []))
        self.height = len(self._rows)

    def iter_rows(self, *, named=False):
        assert named is True
        return iter(self._rows)


def _clock():
    return NOW


def _module(schedule_frame=None, weekly_frame=None):
    schedule_frame = schedule_frame or FakePolarsFrame([{"game_id": "2026_01_A_B"}])
    weekly_frame = weekly_frame or FakePolarsFrame([{"player_id": "p1", "week": 1}])

    def load_schedules(seasons):
        assert seasons == 2026
        return schedule_frame

    def load_player_stats(seasons, summary_level="week"):
        assert seasons == 2026
        assert summary_level == "week"
        return weekly_frame

    return SimpleNamespace(
        __version__="test",
        load_schedules=load_schedules,
        load_player_stats=load_player_stats,
    )


def test_deterministic_digest_is_row_and_mapping_order_independent():
    first = FakePolarsFrame(
        [{"week": 2, "player": "b"}, {"week": 1, "player": "a"}],
        columns=["week", "player"],
    )
    second = FakePolarsFrame(
        [{"player": "a", "week": 1}, {"player": "b", "week": 2}],
        columns=["player", "week"],
    )

    assert deterministic_frame_digest(first) == deterministic_frame_digest(second)


def test_polars_compatible_frames_record_observed_evidence():
    manifest = probe_sources(2026, module=_module(), clock=_clock)

    schedule = manifest["datasets"]["schedules"]
    assert schedule["status"] == "AVAILABLE"
    assert schedule["frame_type"].endswith("FakePolarsFrame")
    assert schedule["row_count"] == 1
    assert schedule["columns"] == ["game_id"]
    assert len(schedule["sha256"]) == 64


def test_missing_loader_symbol_blocks_only_that_dataset():
    module = _module()
    del module.load_schedules

    manifest = probe_sources(2026, module=module, clock=_clock)

    assert manifest["datasets"]["schedules"]["block_reason"] == "MISSING_LOADER_SYMBOL"
    assert manifest["datasets"]["weekly_player_data"]["status"] == "AVAILABLE"


def test_source_exception_is_recorded_and_other_attempt_continues():
    module = _module()

    def broken_schedules(seasons):
        raise RuntimeError("upstream unavailable")

    module.load_schedules = broken_schedules
    manifest = probe_sources(2026, module=module, clock=_clock)

    schedule = manifest["datasets"]["schedules"]
    assert schedule["block_reason"] == "SOURCE_EXCEPTION"
    assert schedule["error"] == "RuntimeError: upstream unavailable"
    assert manifest["datasets"]["weekly_player_data"]["status"] == "AVAILABLE"


def test_empty_loaded_result_is_blocked():
    manifest = probe_sources(
        2026,
        module=_module(schedule_frame=FakePolarsFrame([], columns=["game_id"])),
        clock=_clock,
    )

    schedule = manifest["datasets"]["schedules"]
    assert schedule["status"] == "BLOCKED"
    assert schedule["block_reason"] == "EMPTY_RESULT"
    assert schedule["row_count"] == 0
    assert schedule["sha256"] is None


def test_unsupported_frame_is_blocked_without_masking_successful_load():
    manifest = probe_sources(
        2026,
        module=_module(schedule_frame=[{"game_id": "not-a-frame"}]),
        clock=_clock,
    )

    schedule = manifest["datasets"]["schedules"]
    assert schedule["status"] == "BLOCKED"
    assert schedule["block_reason"] == "UNSUPPORTED_FRAME_TYPE"
    assert schedule["frame_type"] == "builtins.list"


def test_any_dataset_block_keeps_probe_truthfully_blocked():
    module = _module()
    del module.load_schedules

    manifest = probe_sources(2026, module=module, clock=_clock)

    assert manifest["probe_status"] == "BLOCKED"
    assert manifest["source_availability_status"] == "UNKNOWN"
    assert manifest["datasets"]["schedules"]["status"] == "BLOCKED"


def test_probe_success_does_not_claim_later_validation_gates():
    manifest = probe_sources(2026, module=_module(), clock=_clock)

    assert manifest["probe_status"] == "PASS"
    assert manifest["source_availability_status"] == "AVAILABLE"
    assert manifest["week_completeness_status"] == "NOT_EVALUATED"
    assert manifest["export_validation_status"] == "NOT_EVALUATED"


def test_manifest_serialization_creates_local_parent_directories(tmp_path):
    manifest = probe_sources(2026, module=_module(), clock=_clock)
    destination = tmp_path / "nested" / "probe.json"

    written = write_manifest(manifest, destination)

    assert written == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == manifest


def test_dependency_failure_blocks_each_dataset(monkeypatch):
    source_probe_module = importlib.import_module("apexos_in_season.source_probe")

    def missing_dependency(name):
        assert name == "nflreadpy"
        raise ModuleNotFoundError("nflreadpy is not installed")

    monkeypatch.setattr(source_probe_module.importlib, "import_module", missing_dependency)
    manifest = probe_sources(2026, clock=_clock)

    assert manifest["probe_status"] == "BLOCKED"
    assert manifest["source_availability_status"] == "UNKNOWN"
    assert all(
        dataset["block_reason"] == "DEPENDENCY_FAILURE"
        for dataset in manifest["datasets"].values()
    )
