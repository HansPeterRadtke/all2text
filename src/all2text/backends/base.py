from __future__ import annotations

from pathlib import Path
from typing import Protocol

from all2text.models import Classification, ConversionContext, ConversionResult


class ConverterBackend(Protocol):
    name: str

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        ...

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        ...

