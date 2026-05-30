from __future__ import annotations

from collections.abc import Iterable

from all2text.backends import (
    ArchiveBackend,
    BinaryFallbackBackend,
    CadPlaceholderBackend,
    ContainerPlaceholderBackend,
    DatabasePlaceholderBackend,
    DocumentPlaceholderBackend,
    EbookPlaceholderBackend,
    EmailBackend,
    ExecutablePlaceholderBackend,
    FilesystemBackend,
    FontPlaceholderBackend,
    ImagePlaceholderBackend,
    MediaPlaceholderBackend,
    ScientificPlaceholderBackend,
    TextBackend,
)
from all2text.backends.base import ConverterBackend
from all2text.models import Classification


class ConversionRegistry:
    def __init__(self, backends: Iterable[ConverterBackend] | None = None) -> None:
        self._backends: list[ConverterBackend] = list(backends or [])

    def register(self, backend: ConverterBackend) -> None:
        self._backends.append(backend)

    def select(self, classification: Classification, entry_type: str) -> ConverterBackend:
        for backend in self._backends:
            if backend.can_handle(classification, entry_type):
                return backend
        return BinaryFallbackBackend()

    def names(self) -> list[str]:
        return [backend.name for backend in self._backends]


def build_default_registry() -> ConversionRegistry:
    return ConversionRegistry(
        [
            FilesystemBackend(),
            TextBackend(),
            EmailBackend(),
            ArchiveBackend(),
            EbookPlaceholderBackend(),
            DatabasePlaceholderBackend(),
            ImagePlaceholderBackend(),
            MediaPlaceholderBackend(),
            DocumentPlaceholderBackend(),
            ScientificPlaceholderBackend(),
            CadPlaceholderBackend(),
            FontPlaceholderBackend(),
            ExecutablePlaceholderBackend(),
            ContainerPlaceholderBackend(),
            BinaryFallbackBackend(),
        ]
    )

