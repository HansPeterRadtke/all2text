from __future__ import annotations

from all2text.backends.archive import ArchiveBackend
from all2text.backends.binary import BinaryFallbackBackend
from all2text.backends.cad import CadPlaceholderBackend
from all2text.backends.containers import ContainerPlaceholderBackend
from all2text.backends.database import DatabasePlaceholderBackend
from all2text.backends.documents import DocumentPlaceholderBackend
from all2text.backends.ebook import EbookPlaceholderBackend
from all2text.backends.email import EmailBackend
from all2text.backends.executable import ExecutablePlaceholderBackend
from all2text.backends.filesystem import FilesystemBackend
from all2text.backends.font import FontPlaceholderBackend
from all2text.backends.geospatial import GeospatialPlaceholderBackend
from all2text.backends.image import ImagePlaceholderBackend
from all2text.backends.media import MediaPlaceholderBackend
from all2text.backends.scientific import ScientificPlaceholderBackend
from all2text.backends.text import TextBackend

__all__ = [
    "ArchiveBackend",
    "BinaryFallbackBackend",
    "CadPlaceholderBackend",
    "ContainerPlaceholderBackend",
    "DatabasePlaceholderBackend",
    "DocumentPlaceholderBackend",
    "EbookPlaceholderBackend",
    "EmailBackend",
    "ExecutablePlaceholderBackend",
    "FilesystemBackend",
    "FontPlaceholderBackend",
    "GeospatialPlaceholderBackend",
    "ImagePlaceholderBackend",
    "MediaPlaceholderBackend",
    "ScientificPlaceholderBackend",
    "TextBackend",
]
