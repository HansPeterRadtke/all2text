from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

EntryType = Literal["directory", "file", "symlink", "other"]


@dataclass
class RunOptions:
    profile: str = "auto"
    max_header_bytes: int = 4096
    max_hash_bytes: int = 256 * 1024 * 1024
    max_binary_sample_bytes: int = 1024 * 1024
    max_archive_members: int = 5000
    use_file_command: bool = True
    auto_detect_python: bool = True
    auto_detect_tools: bool = True
    auto_detect_local_models: bool = True
    allow_optional_python: bool = True
    allow_external_tools: bool = True
    allow_local_models: bool = True
    copy_source_stat: bool = True
    reject_target_inside_source: bool = True


@dataclass
class TreeEntry:
    source_path: Path
    relative_path: Path
    entry_type: EntryType
    link_target: str | None = None
    scan_errors: list[str] = field(default_factory=list)
    scan_warnings: list[str] = field(default_factory=list)

    @property
    def produces_text(self) -> bool:
        return self.entry_type != "directory"


@dataclass
class PlannedOutput:
    source_relative_path: str
    target_relative_path: str
    output_path: Path
    collision: bool = False
    collision_reason: str | None = None


@dataclass
class LayerEvidence:
    source: str
    rough_category: str | None = None
    concrete_format: str | None = None
    confidence: str = "none"
    details: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Classification:
    extension_hint: LayerEvidence
    name_hint: LayerEvidence
    mime_hint: LayerEvidence
    content_signature: LayerEvidence
    rough_category: str
    concrete_format: str
    content_profile: str
    confidence: str
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_textual: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension_hint": self.extension_hint.to_dict(),
            "name_hint": self.name_hint.to_dict(),
            "mime_hint": self.mime_hint.to_dict(),
            "content_signature": self.content_signature.to_dict(),
            "rough_category": self.rough_category,
            "concrete_format": self.concrete_format,
            "content_profile": self.content_profile,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "is_textual": self.is_textual,
        }


@dataclass
class ConversionContext:
    source_root: Path
    target_root: Path
    options: RunOptions
    config: Any | None = None


@dataclass
class ConversionResult:
    text: str
    converter_used: str
    extraction_methods_used: list[str] = field(default_factory=list)
    llm_used: bool = False
    ocr_used: bool = False
    vlm_used: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
