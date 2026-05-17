"""Opt-in JSONL capture recorder for MQTT callback traces."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaptureRecorder:
    def __init__(self, path: Path | None) -> None:
        self._path = Path(path) if path is not None else None

    @classmethod
    def from_env(cls, device_name: str) -> CaptureRecorder:
        capture_dir = os.environ.get("MAMMOTION_LITE_CAPTURE_DIR")
        if capture_dir is None:
            return cls(None)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = Path(capture_dir) / f"{device_name}-{stamp}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(path)

    def record(self, kind: str, payload: Any) -> None:
        if self._path is None:
            return
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
        }
        to_dict = getattr(payload, "to_dict", None)
        if callable(to_dict):
            entry["payload_type"] = type(payload).__name__
            entry["payload"] = to_dict()
        else:
            entry["payload"] = payload
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
