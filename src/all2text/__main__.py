"""Module execution entry point for ``python -m all2text``."""

from __future__ import annotations

import sys

from all2text.cli import main


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main(sys.argv[1:]))
