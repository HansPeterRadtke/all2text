from __future__ import annotations

from pathlib import Path

from all2text.models import Classification, ConversionContext, ConversionResult


class FilesystemBackend:
    name = "filesystem_metadata_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type in {"symlink", "other"}

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        if str(metadata.get("entry_type")) == "symlink":
            text = "\n".join(
                [
                    "Filesystem link:",
                    f"- relative_path: {rel_path.as_posix()}",
                    f"- link_target: {metadata.get('link_target') or '<unavailable>'}",
                    "- policy: symlinks are recorded but not followed during conversion.",
                ]
            )
            return ConversionResult(
                text=text + "\n",
                converter_used="symlink_metadata_backend",
                extraction_methods_used=["symlink_target_record"],
                warnings=["symlink_not_followed"],
                limitations=["Symlink target content was not read or converted."],
            )
        text = "\n".join(
            [
                "Filesystem entry:",
                f"- relative_path: {rel_path.as_posix()}",
                f"- entry_type: {metadata.get('entry_type')}",
                "- policy: non-regular filesystem entries are described but not read as files.",
            ]
        )
        return ConversionResult(
            text=text + "\n",
            converter_used="non_regular_entry_backend",
            extraction_methods_used=["filesystem_entry_notice"],
            warnings=[f"non_regular_entry:{metadata.get('entry_type')}"],
            limitations=["Non-regular entry content was not read."],
        )

