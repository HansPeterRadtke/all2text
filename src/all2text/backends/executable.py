from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class ExecutablePlaceholderBackend:
    name = "executable_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "executable_or_binary"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        schema, warnings, methods = executable_schema_probe(path, classification)
        limitation = (
            "Executable/binary conversion emits bounded metadata only. No execution, disassembly, "
            "decompilation, unpacking, or behavioral claims are performed."
        )
        extra = [f"- limitation: {limitation}"]
        if schema:
            extra.extend(["- schema_probe:", json.dumps(schema, ensure_ascii=False, sort_keys=True)[:4000]])
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Executable/binary safe summary",
                extra_lines=extra,
            ),
            converter_used=self.name,
            extraction_methods_used=["executable_placeholder_summary", *methods],
            warnings=warnings,
            metadata={"schema_probe": schema},
            limitations=[limitation],
        )


def executable_schema_probe(path: Path, classification: Classification) -> tuple[dict[str, Any], list[str], list[str]]:
    with path.open("rb") as handle:
        header = handle.read(4096)
    if header.startswith(b"MZ"):
        schema, warnings, methods = pe_schema(path)
        return augment_lief_schema(path, schema, warnings, methods)
    if header.startswith(b"\xcf\xfa\xed\xfe") or header.startswith(b"\xfe\xed\xfa\xcf") or header.startswith(b"\xca\xfe\xba\xbe"):
        schema, warnings, methods = macho_schema(path)
        return augment_lief_schema(path, schema, warnings, methods)
    if header.startswith(b"\x7fELF"):
        schema, warnings, methods = elf_header_schema(header)
        return augment_lief_schema(path, schema, warnings, methods)
    return {}, [], []


def pe_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import pefile
    except Exception as exc:
        return {}, [f"pefile_unavailable:{exc}"], []
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
            ]
        )
        imports = []
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])[:50]:
            imports.append(
                {
                    "dll": str(entry.dll.decode("utf-8", errors="replace")),
                    "symbols": [
                        str(item.name.decode("utf-8", errors="replace"))
                        for item in getattr(entry, "imports", [])[:50]
                        if item.name
                    ],
                }
            )
        exports = []
        export_dir = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
        if export_dir is not None:
            exports = [
                str(symbol.name.decode("utf-8", errors="replace"))
                for symbol in getattr(export_dir, "symbols", [])[:100]
                if symbol.name
            ]
        schema = {
            "provider": "pefile",
            "format": "pe",
            "machine": hex(int(pe.FILE_HEADER.Machine)),
            "section_count": int(pe.FILE_HEADER.NumberOfSections),
            "imports": imports,
            "exports": exports,
            "code_executed": False,
        }
        pe.close()
        return schema, [], ["pefile_metadata_probe"]
    except Exception as exc:
        return {}, [f"pefile_metadata_probe_failed:{exc}"], []


def macho_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        from macholib.MachO import MachO
    except Exception as exc:
        return {}, [f"macholib_unavailable:{exc}"], []
    try:
        macho = MachO(str(path))
        headers = [
            {
                "cputype": str(header.header.cputype),
                "filetype": str(header.header.filetype),
                "command_count": int(header.header.ncmds),
            }
            for header in macho.headers[:20]
        ]
        return {"provider": "macholib", "format": "mach-o", "headers": headers, "code_executed": False}, [], ["macholib_metadata_probe"]
    except Exception as exc:
        return {}, [f"macholib_metadata_probe_failed:{exc}"], []


def elf_header_schema(header: bytes) -> tuple[dict[str, Any], list[str], list[str]]:
    if len(header) < 20:
        return {}, ["elf_header_too_short"], []
    bits = 64 if header[4] == 2 else 32 if header[4] == 1 else None
    endian = "little" if header[5] == 1 else "big" if header[5] == 2 else "unknown"
    return {
        "provider": "stdlib_header_parser",
        "format": "elf",
        "bits": bits,
        "endianness": endian,
        "elf_type": int.from_bytes(header[16:18], endian if endian in {"little", "big"} else "little"),
        "machine": int.from_bytes(header[18:20], endian if endian in {"little", "big"} else "little"),
        "code_executed": False,
        "sections_dumped": False,
    }, [], ["elf_header_metadata_probe"]


def augment_lief_schema(
    path: Path,
    schema: dict[str, Any],
    warnings: list[str],
    methods: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    lief, lief_warnings, lief_methods = lief_schema(path)
    if lief:
        schema = dict(schema)
        schema["lief"] = lief
        methods = [*methods, *lief_methods]
    return schema, [*warnings, *lief_warnings], methods


def lief_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import lief
    except Exception as exc:
        return {}, [f"lief_unavailable:{exc}"], []
    try:
        parsed = lief.parse(str(path))
    except Exception as exc:
        return {}, [f"lief_metadata_probe_failed:{exc}"], []
    if parsed is None:
        return {}, ["lief_metadata_probe_unrecognized_binary"], []
    try:
        sections = getattr(parsed, "sections", []) or []
        libraries = getattr(parsed, "libraries", []) or []
        imported_functions = getattr(parsed, "imported_functions", []) or []
        exported_functions = getattr(parsed, "exported_functions", []) or []
        schema = {
            "provider": "lief",
            "format": str(getattr(parsed, "format", type(parsed).__name__)),
            "entrypoint": getattr(parsed, "entrypoint", None),
            "section_count": len(sections),
            "sections_sample": [str(getattr(section, "name", "")) for section in list(sections)[:50]],
            "libraries_sample": [str(item) for item in list(libraries)[:50]],
            "imported_function_sample": [str(item) for item in list(imported_functions)[:100]],
            "exported_function_sample": [str(item) for item in list(exported_functions)[:100]],
            "code_executed": False,
            "disassembled": False,
        }
        return schema, [], ["lief_metadata_probe"]
    except Exception as exc:
        return {}, [f"lief_metadata_probe_failed:{exc}"], []
