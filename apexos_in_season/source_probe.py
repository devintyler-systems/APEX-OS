"""Read-only availability probes for the approved in-season nflverse sources.

This module deliberately stops at source discovery.  It does not define player-week
keys, validate week completeness, or produce an analytical export.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import json
import math
import sys
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable


UNKNOWN = "UNKNOWN"
NOT_EVALUATED = "NOT_EVALUATED"

_DATASET_SPECS: dict[str, dict[str, Any]] = {
    "schedules": {
        "loader_symbol": "load_schedules",
        "arguments": lambda season: {"seasons": season},
    },
    "weekly_player_data": {
        "loader_symbol": "load_player_stats",
        "arguments": lambda season: {
            "seasons": season,
            "summary_level": "week",
        },
    },
}


class UnsupportedFrameError(ValueError):
    """Raised when a loader result cannot be inspected without assumptions."""


def _qualified_type(value: Any) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_value(value: Any) -> Any:
    """Convert common frame scalar values into stable JSON-compatible values."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"__float__": "NaN"}
        if math.isinf(value):
            return {"__float__": "Infinity" if value > 0 else "-Infinity"}
        return value
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, time):
        return {"__time__": value.isoformat()}
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalise_value(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        item = item_method()
        if item is not value:
            return _normalise_value(item)

    return {"__type__": _qualified_type(value), "__value__": str(value)}


def _polars_compatible_rows(frame: Any) -> tuple[list[str], int, list[Mapping[str, Any]]]:
    """Extract rows through the public interface shared by Polars DataFrames."""

    columns_value = getattr(frame, "columns", None)
    height_value = getattr(frame, "height", None)
    iter_rows = getattr(frame, "iter_rows", None)
    if not isinstance(columns_value, Iterable) or isinstance(columns_value, (str, bytes)):
        raise UnsupportedFrameError("result has no Polars-compatible columns collection")
    if not isinstance(height_value, int) or height_value < 0:
        raise UnsupportedFrameError("result has no non-negative Polars-compatible height")
    if not callable(iter_rows):
        raise UnsupportedFrameError("result has no Polars-compatible iter_rows method")

    columns = [str(column) for column in columns_value]
    try:
        rows = list(iter_rows(named=True))
    except Exception as exc:
        raise UnsupportedFrameError(
            f"Polars-compatible row iteration failed: {type(exc).__name__}: {exc}"
        ) from exc
    if any(not isinstance(row, Mapping) for row in rows):
        raise UnsupportedFrameError("Polars-compatible named rows were not mappings")
    if len(rows) != height_value:
        raise UnsupportedFrameError(
            f"reported height {height_value} does not match iterated row count {len(rows)}"
        )
    return columns, height_value, rows


def frame_evidence(frame: Any) -> dict[str, Any]:
    """Return inspectable evidence for a Polars or Polars-compatible frame."""

    columns, row_count, rows = _polars_compatible_rows(frame)
    canonical_columns = sorted(columns)
    canonical_rows = []
    for row in rows:
        normalised = {
            column: _normalise_value(row.get(column)) for column in canonical_columns
        }
        canonical_rows.append(
            json.dumps(normalised, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    canonical_rows.sort()
    payload = json.dumps(
        {"columns": canonical_columns, "rows": canonical_rows},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "frame_type": _qualified_type(frame),
        "row_count": row_count,
        "columns": columns,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def deterministic_frame_digest(frame: Any) -> str:
    """Compute the canonical digest used in dataset evidence."""

    return str(frame_evidence(frame)["sha256"])


def _json_safe(value: Any) -> Any:
    normalised = _normalise_value(value)
    json.dumps(normalised, sort_keys=True)
    return normalised


def _exposed_metadata(loader: Callable[..., Any], frame: Any) -> tuple[Any, Any]:
    """Read only metadata directly attached to the loader/result objects."""

    direct: dict[str, Any] = {}
    for obj in (loader, frame):
        namespace = getattr(obj, "__dict__", None)
        if isinstance(namespace, Mapping):
            direct.update(namespace)
            attrs = namespace.get("attrs")
            if isinstance(attrs, Mapping):
                direct.update(attrs)

    source_reference = None
    for key in ("source_reference", "source_url", "release_url"):
        value = direct.get(key)
        if value not in (None, ""):
            source_reference = _json_safe(value)
            break

    source_update_metadata: Any = UNKNOWN
    for key in (
        "source_update_metadata",
        "release_metadata",
        "release_date",
        "updated_at",
    ):
        value = direct.get(key)
        if value not in (None, ""):
            source_update_metadata = _json_safe(value)
            break
    return source_reference, source_update_metadata


def _base_dataset_result(retrieval_utc: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "loader_symbol": None,
        "invocation": None,
        "frame_type": None,
        "row_count": 0,
        "columns": [],
        "sha256": None,
        "retrieval_utc": retrieval_utc,
        "source_reference": None,
        "source_update_metadata": UNKNOWN,
        "block_reason": None,
        "error": None,
    }


def _loader_signature(loader: Callable[..., Any]) -> inspect.Signature:
    return inspect.signature(loader)


def _accepts_keyword(signature: inspect.Signature, keyword: str) -> bool:
    parameter = signature.parameters.get(keyword)
    if parameter is not None:
        return parameter.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    return any(
        item.kind is inspect.Parameter.VAR_KEYWORD
        for item in signature.parameters.values()
    )


def _invocation_text(symbol: str, arguments: Mapping[str, Any]) -> str:
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    return f"nflreadpy.{symbol}({rendered})"


def _probe_dataset(
    module: Any,
    dataset_name: str,
    season: int,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    spec = _DATASET_SPECS[dataset_name]
    symbol = str(spec["loader_symbol"])
    result = _base_dataset_result(_utc_text(clock()))
    loader = getattr(module, symbol, None)
    if not callable(loader):
        result["block_reason"] = "MISSING_LOADER_SYMBOL"
        result["error"] = f"nflreadpy has no callable public loader {symbol!r}"
        return result

    result["loader_symbol"] = symbol
    arguments = spec["arguments"](season)
    try:
        signature = _loader_signature(loader)
    except Exception as exc:
        result["block_reason"] = "INCOMPATIBLE_LOADER_SIGNATURE"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    missing_keywords = [
        keyword for keyword in arguments if not _accepts_keyword(signature, keyword)
    ]
    if missing_keywords:
        result["block_reason"] = "INCOMPATIBLE_LOADER_SIGNATURE"
        result["error"] = (
            f"observed signature {signature} does not accept keyword(s): "
            + ", ".join(missing_keywords)
        )
        return result

    result["invocation"] = _invocation_text(symbol, arguments)
    try:
        frame = loader(**arguments)
    except Exception as exc:
        result["retrieval_utc"] = _utc_text(clock())
        result["block_reason"] = "SOURCE_EXCEPTION"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["retrieval_utc"] = _utc_text(clock())
    result["frame_type"] = _qualified_type(frame)
    try:
        evidence = frame_evidence(frame)
    except UnsupportedFrameError as exc:
        result["block_reason"] = "UNSUPPORTED_FRAME_TYPE"
        result["error"] = str(exc)
        return result
    except Exception as exc:
        result["block_reason"] = "UNSUPPORTED_FRAME_TYPE"
        result["error"] = f"frame inspection failed: {type(exc).__name__}: {exc}"
        return result

    result.update(evidence)
    source_reference, source_update_metadata = _exposed_metadata(loader, frame)
    result["source_reference"] = source_reference
    result["source_update_metadata"] = source_update_metadata
    if result["row_count"] == 0:
        result["sha256"] = None
        result["block_reason"] = "EMPTY_RESULT"
        result["error"] = "loader returned a frame with zero rows"
        return result

    result["status"] = "AVAILABLE"
    return result


def _package_version(module: Any) -> str:
    try:
        return importlib.metadata.version("nflreadpy")
    except importlib.metadata.PackageNotFoundError:
        value = getattr(module, "__version__", UNKNOWN)
        return str(value)


def _relevant_loader_symbols(module: Any) -> list[dict[str, str]]:
    symbols: list[dict[str, str]] = []
    for symbol in sorted({spec["loader_symbol"] for spec in _DATASET_SPECS.values()}):
        loader = getattr(module, symbol, None)
        if not callable(loader):
            continue
        try:
            signature = str(_loader_signature(loader))
        except Exception as exc:
            signature = f"UNAVAILABLE ({type(exc).__name__}: {exc})"
        symbols.append({"symbol": str(symbol), "signature": signature})
    return symbols


def _dependency_blocked_manifest(
    season: int,
    clock: Callable[[], datetime],
    exc: Exception,
) -> dict[str, Any]:
    generated_at = _utc_text(clock())
    error = f"{type(exc).__name__}: {exc}"
    datasets = {}
    for dataset_name in _DATASET_SPECS:
        item = _base_dataset_result(generated_at)
        item["block_reason"] = "DEPENDENCY_FAILURE"
        item["error"] = error
        datasets[dataset_name] = item
    return {
        "contract_version": "1.1",
        "season": season,
        "generated_at_utc": generated_at,
        "python_version": sys.version.split()[0],
        "nflreadpy_version": UNKNOWN,
        "relevant_loader_symbols": [],
        "probe_status": "BLOCKED",
        "source_availability_status": "UNKNOWN",
        "week_completeness_status": NOT_EVALUATED,
        "export_validation_status": NOT_EVALUATED,
        "datasets": datasets,
    }


def probe_sources(
    season: int,
    *,
    module: Any | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    """Probe approved upstream datasets without writing their returned rows."""

    if module is None:
        try:
            module = importlib.import_module("nflreadpy")
        except Exception as exc:
            return _dependency_blocked_manifest(season, clock, exc)

    datasets = {
        name: _probe_dataset(module, name, season, clock) for name in _DATASET_SPECS
    }
    all_available = all(item["status"] == "AVAILABLE" for item in datasets.values())
    if all_available:
        source_availability_status = "AVAILABLE"
    elif any(
        item["block_reason"] in {"SOURCE_EXCEPTION", "EMPTY_RESULT"}
        for item in datasets.values()
    ):
        source_availability_status = "UNAVAILABLE"
    else:
        source_availability_status = "UNKNOWN"

    return {
        "contract_version": "1.1",
        "season": season,
        "generated_at_utc": _utc_text(clock()),
        "python_version": sys.version.split()[0],
        "nflreadpy_version": _package_version(module),
        "relevant_loader_symbols": _relevant_loader_symbols(module),
        "probe_status": "PASS" if all_available else "BLOCKED",
        "source_availability_status": source_availability_status,
        "week_completeness_status": NOT_EVALUATED,
        "export_validation_status": NOT_EVALUATED,
        "datasets": datasets,
    }


def write_manifest(manifest: Mapping[str, Any], path: str | Path) -> Path:
    """Serialize probe evidence locally; upstream loaders never receive this path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination
