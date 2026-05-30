from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class MediaPlaceholderBackend:
    name = "media_metadata_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category in {"audio", "video"}

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Media conversion is metadata-only in the core package. Speech transcription, frame OCR, "
            "scene detection, and visual understanding require optional backends."
        )
        ffprobe_metadata, warnings = ffprobe(path)
        extra = [f"- limitation: {limitation}"]
        if ffprobe_metadata:
            extra.append("- ffprobe_metadata_available: true")
        text = binary_summary_text(path, classification, ctx, heading="Media safe summary", extra_lines=extra)
        if ffprobe_metadata:
            text += "\nffprobe metadata:\n" + json.dumps(ffprobe_metadata, indent=2, ensure_ascii=False) + "\n"
        elif warnings:
            text += "\nffprobe status:\n" + "\n".join(f"- {warning}" for warning in warnings) + "\n"
        methods = ["media_placeholder_metadata"]
        if ffprobe_metadata:
            methods.append("ffprobe_metadata")
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=methods,
            warnings=warnings,
            metadata={"ffprobe": ffprobe_metadata or None},
            limitations=[limitation],
        )


def ffprobe(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None, ["ffprobe_unavailable"]
    try:
        completed = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        return None, [f"ffprobe_error:{exc}"]
    if completed.returncode != 0:
        return None, [f"ffprobe_exit_code:{completed.returncode}", f"ffprobe_stderr:{completed.stderr.strip()}"]
    try:
        return json.loads(completed.stdout or "{}"), []
    except Exception:
        return {"raw_stdout": completed.stdout[:4000]}, ["ffprobe_json_parse_failed"]

