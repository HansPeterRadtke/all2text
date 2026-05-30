from __future__ import annotations

import sqlite3
from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class DatabasePlaceholderBackend:
    name = "database_metadata_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "database"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Database conversion is schema/metadata-only in the core package. Table data is not dumped "
            "unless a database-specific backend is configured."
        )
        db_meta, warnings = sqlite_metadata(path, classification)
        extra = [f"- limitation: {limitation}"]
        if db_meta:
            extra.append("- database_metadata: " + repr(db_meta))
        text = binary_summary_text(path, classification, ctx, heading="Database safe summary", extra_lines=extra)
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=["database_placeholder_summary", "sqlite_schema_probe"],
            warnings=warnings,
            metadata={"database": db_meta},
            limitations=[limitation],
        )


def sqlite_metadata(path: Path, classification: Classification) -> tuple[dict[str, object], list[str]]:
    if "SQLITE" not in classification.concrete_format.upper():
        return {}, ["database_schema_probe_skipped_for_non_sqlite"]
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except Exception as exc:
        return {}, [f"sqlite_open_failed:{exc}"]
    try:
        rows = con.execute(
            "select type, name, tbl_name from sqlite_master where name not like 'sqlite_%' order by type, name"
        ).fetchall()
        return {
            "sqlite_objects": [
                {"type": str(row[0]), "name": str(row[1]), "table_name": str(row[2])} for row in rows
            ],
            "object_count": len(rows),
        }, []
    except Exception as exc:
        return {}, [f"sqlite_schema_probe_failed:{exc}"]
    finally:
        con.close()

