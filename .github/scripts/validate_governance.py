#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from governance import validate_repository


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Governance validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
