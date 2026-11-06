"""Loads labelled bug reports. Any pipe-separated file with the same header works."""
from __future__ import annotations

import csv
from pathlib import Path

REQUIRED_COLUMNS = {"group", "component", "priority", "severity", "title", "description"}


def load_dataset(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|", quoting=csv.QUOTE_NONE)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        records = []
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"{path}:{line} has too many columns")
            record = {key: (value or "").strip() for key, value in row.items()}
            # Reports without a group are their own group, so every group id is usable.
            record["group"] = record["group"] or f"single-{line}"
            record["steps_to_reproduce"] = "\n".join(
                f"{i}. {step.strip()}" for i, step in enumerate(record.pop("steps", "").split(";"), start=1)
                if step.strip()
            )
            record["expected_behavior"] = record.pop("expected", "")
            record["actual_behavior"] = record.pop("actual", "")
            record["stack_trace"] = record.pop("stack", "")
            records.append(record)
    return records
