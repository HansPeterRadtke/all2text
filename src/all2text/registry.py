from __future__ import annotations

from collections.abc import Iterable

from all2text.config import All2TextConfig, config_for_context
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
    GeospatialPlaceholderBackend,
    ImagePlaceholderBackend,
    MediaPlaceholderBackend,
    ScientificPlaceholderBackend,
    TextBackend,
)
from all2text.backends.base import ConverterBackend
from all2text.models import Classification


class ConversionRegistry:
    def __init__(
        self,
        backends: Iterable[ConverterBackend] | None = None,
        *,
        preferred: dict[str, str] | None = None,
    ) -> None:
        self._backends: list[ConverterBackend] = list(backends or [])
        self._preferred = dict(preferred or {})

    def register(self, backend: ConverterBackend) -> None:
        self._backends.append(backend)

    def select(self, classification: Classification, entry_type: str) -> ConverterBackend:
        preferred = self._preferred_backend(classification, entry_type)
        if preferred is not None and preferred.can_handle(classification, entry_type):
            return preferred
        for backend in self._backends:
            if backend.can_handle(classification, entry_type):
                return backend
        return BinaryFallbackBackend()

    def names(self) -> list[str]:
        return [backend.name for backend in self._backends]

    def preferred_backends(self) -> dict[str, str]:
        return dict(self._preferred)

    def _preferred_backend(self, classification: Classification, entry_type: str) -> ConverterBackend | None:
        keys = [entry_type, classification.rough_category, classification.concrete_format.casefold()]
        for key in keys:
            backend_name = self._preferred.get(str(key))
            if not backend_name:
                continue
            backend = next((item for item in self._backends if item.name == backend_name), None)
            if backend is not None:
                return backend
        return None


def build_default_registry(config: All2TextConfig | None = None) -> ConversionRegistry:
    cfg = config_for_context(config)
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
            GeospatialPlaceholderBackend(),
            CadPlaceholderBackend(),
            FontPlaceholderBackend(),
            ExecutablePlaceholderBackend(),
            ContainerPlaceholderBackend(),
            BinaryFallbackBackend(),
        ],
        preferred={key: value.backend for key, value in cfg.modules.items()},
    )
