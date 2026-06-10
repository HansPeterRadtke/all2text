from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class ScientificPlaceholderBackend:
    name = "scientific_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "scientific_data"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        schema, schema_warnings, methods = scientific_schema_probe(path, classification)
        limitation = (
            "Scientific data conversion emits bounded schema/metadata only. It does not dump large "
            "arrays, execute code, or infer domain meaning."
        )
        extra = [f"- limitation: {limitation}"]
        if schema:
            extra.extend(["- schema_probe:", json.dumps(schema, ensure_ascii=False, sort_keys=True)[:4000]])
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Scientific data safe summary",
                extra_lines=extra,
            ),
            converter_used=self.name,
            extraction_methods_used=["scientific_placeholder_summary", *methods],
            warnings=schema_warnings,
            metadata={"schema_probe": schema},
            limitations=[limitation],
        )


def scientific_schema_probe(path: Path, classification: Classification) -> tuple[dict[str, Any], list[str], list[str]]:
    fmt = classification.concrete_format.upper()
    if fmt in {"NUMPY NPY", "NPY"} or path.suffix.casefold() == ".npy":
        return numpy_schema(path)
    if fmt in {"NUMPY NPZ", "NPZ"} or path.suffix.casefold() == ".npz":
        return numpy_npz_schema(path)
    if fmt in {"HDF5"}:
        return hdf5_schema(path)
    if "NETCDF" in fmt:
        return netcdf_schema(path)
    if fmt == "FITS":
        return fits_schema(path)
    if fmt == "PARQUET":
        return parquet_schema(path)
    if "MATLAB" in fmt:
        return matlab_schema(path)
    return {}, [], []


def numpy_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import numpy as np

        array = np.load(path, mmap_mode="r", allow_pickle=False)
        return (
            {
                "provider": "numpy",
                "format": "npy",
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "ndim": int(array.ndim),
                "size": int(array.size),
                "array_values_dumped": False,
            },
            [],
            ["numpy_schema_probe"],
        )
    except Exception as exc:
        return {}, [f"numpy_schema_probe_failed:{exc}"], []


def numpy_npz_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import numpy as np

        result: dict[str, Any] = {"provider": "numpy", "format": "npz", "members": []}
        with np.load(path, allow_pickle=False) as archive:
            for name in list(archive.files)[:100]:
                array = archive[name]
                result["members"].append(
                    {"name": name, "shape": list(array.shape), "dtype": str(array.dtype), "ndim": int(array.ndim)}
                )
            result["member_count"] = len(archive.files)
            result["truncated"] = len(archive.files) > 100
        return result, [], ["numpy_npz_schema_probe"]
    except Exception as exc:
        return {}, [f"numpy_npz_schema_probe_failed:{exc}"], []


def hdf5_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import h5py
    except Exception as exc:
        return {}, [f"h5py_unavailable:{exc}"], []
    try:
        items: list[dict[str, Any]] = []
        with h5py.File(path, "r") as handle:
            def visitor(name: str, obj: Any) -> None:
                if len(items) >= 200:
                    return
                kind = "dataset" if hasattr(obj, "shape") else "group"
                items.append(
                    {
                        "path": name,
                        "kind": kind,
                        "shape": list(getattr(obj, "shape", []) or []),
                        "dtype": str(getattr(obj, "dtype", "")) or None,
                    }
                )

            handle.visititems(visitor)
        return {"provider": "h5py", "format": "hdf5", "items": items, "truncated": len(items) >= 200}, [], ["h5py_schema_probe"]
    except Exception as exc:
        return {}, [f"h5py_schema_probe_failed:{exc}"], []


def netcdf_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    try:
        import netCDF4
    except Exception as exc:
        warnings.append(f"netCDF4_unavailable:{exc}")
    else:
        try:
            return netcdf_schema_with_module(netCDF4, path), [], ["netcdf_schema_probe"]
        except Exception as exc:
            warnings.append(f"netcdf_schema_probe_failed:{exc}")
    schema, warning = netcdf_schema_subprocess(path)
    if schema:
        if warnings:
            schema = dict(schema)
            schema["fallback_warnings"] = warnings
        return schema, [], ["netcdf_subprocess_schema_probe"]
    return {}, [*warnings, warning], []


def netcdf_schema_with_module(netCDF4: Any, path: Path) -> dict[str, Any]:
    with netCDF4.Dataset(path, "r") as dataset:
        variables = [
            {"name": name, "dimensions": list(var.dimensions), "shape": list(var.shape), "dtype": str(var.dtype)}
            for name, var in list(dataset.variables.items())[:100]
        ]
        dimensions = {name: int(len(value)) for name, value in dataset.dimensions.items()}
    return {"provider": "netCDF4", "format": "netcdf", "dimensions": dimensions, "variables": variables}


def netcdf_schema_subprocess(path: Path, timeout_seconds: int = 30) -> tuple[dict[str, Any], str]:
    script = """
import json, sys
import netCDF4
with netCDF4.Dataset(sys.argv[1], 'r') as dataset:
    variables = [
        {'name': name, 'dimensions': list(var.dimensions), 'shape': list(var.shape), 'dtype': str(var.dtype)}
        for name, var in list(dataset.variables.items())[:100]
    ]
    dimensions = {name: int(len(value)) for name, value in dataset.dimensions.items()}
print(json.dumps({'provider': 'netCDF4', 'format': 'netcdf', 'dimensions': dimensions, 'variables': variables}))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        return {}, f"netcdf_subprocess_schema_probe_failed:{type(exc).__name__}:{exc}"
    if completed.returncode != 0:
        return {}, "netcdf_subprocess_schema_probe_failed:" + completed.stderr[-500:]
    try:
        return json.loads(completed.stdout), ""
    except Exception as exc:
        return {}, f"netcdf_subprocess_schema_probe_bad_json:{type(exc).__name__}:{exc}"


def fits_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        from astropy.io import fits
    except Exception as exc:
        return {}, [f"astropy_unavailable:{exc}"], []
    try:
        with fits.open(path, memmap=True) as hdus:
            records = []
            for index, hdu in enumerate(hdus[:50]):
                data = getattr(hdu, "data", None)
                records.append(
                    {
                        "index": index,
                        "name": str(getattr(hdu, "name", "")),
                        "shape": list(getattr(data, "shape", []) or []),
                        "dtype": str(getattr(data, "dtype", "")) if data is not None else None,
                    }
                )
        return {"provider": "astropy", "format": "fits", "hdus": records, "truncated": len(records) >= 50}, [], ["fits_schema_probe"]
    except Exception as exc:
        return {}, [f"fits_schema_probe_failed:{exc}"], []


def parquet_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import pyarrow.parquet as pq
    except Exception as exc:
        return {}, [f"pyarrow_unavailable:{exc}"], []
    try:
        metadata = pq.read_metadata(path)
        schema = metadata.schema.to_arrow_schema()
        fields = [{"name": field.name, "type": str(field.type)} for field in schema][:200]
        return {
            "provider": "pyarrow",
            "format": "parquet",
            "num_rows": metadata.num_rows,
            "num_row_groups": metadata.num_row_groups,
            "fields": fields,
        }, [], ["parquet_schema_probe"]
    except Exception as exc:
        return {}, [f"parquet_schema_probe_failed:{exc}"], []


def matlab_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        from scipy.io import whosmat
    except Exception as exc:
        return {}, [f"scipy_unavailable:{exc}"], []
    try:
        variables = [
            {"name": name, "shape": list(shape), "class": class_name}
            for name, shape, class_name in whosmat(path)[:200]
        ]
        return {"provider": "scipy", "format": "matlab", "variables": variables}, [], ["matlab_schema_probe"]
    except Exception as exc:
        return {}, [f"matlab_schema_probe_failed:{exc}"], []
