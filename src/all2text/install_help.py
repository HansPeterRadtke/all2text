"""Human-readable external tool installation guidance."""

from __future__ import annotations

import platform
import textwrap


def install_tools_guidance(system: str | None = None) -> str:
    """Return OS-aware guidance for non-PyPI external tools and model servers."""
    name = (system or platform.system()).lower()
    if name.startswith("linux"):
        body = """
        all2text itself is installed with: python -m pip install .
        Source installs can invoke the external setup hook. Inspect or rerun setup with:
          python -m all2text setup --dry-run --profile full

        Interactive source installs can ask a yes/no setup question. Noninteractive installs never
        wait; use ALL2TEXT_SETUP_ASSUME_YES=1 for unattended setup. Built wheels cannot run arbitrary
        postinstall code, so all2text setup remains the manual rerun. Common Debian/Ubuntu package commands:
          sudo apt-get update
          sudo apt-get install -y ffmpeg tesseract-ocr libmagic1 file acl libreoffice

        llama.cpp and model files are intentionally external. Start an OpenAI-compatible llama.cpp
        server, then all2text will probe configured/common local endpoints such as 127.0.0.1:14829
        for text and 127.0.0.1:14830 for vision. Use all2text doctor to see what was found.

        Optional provider Python packages that are usually safe when wheels exist can be installed
        with binary-only pip first, for example:
          python -m pip install --only-binary=:all: mutagen h5py netCDF4 astropy pyarrow ezdxf pyshp pyproj pefile macholib lief faster-whisper

        Heavy document/VLM/ASR/diarization model weights are never downloaded by default. Put them
        under an external model root such as /data/models, or select a bounded setup model
        explicitly. Large isolated provider environments can be bounded with
        ALL2TEXT_SETUP_COMMAND_TIMEOUT_SECONDS. Avoid installing Jetson Torch/torchaudio
        replacements unless they match NVIDIA's local PyTorch build.
        """
    elif name.startswith("windows"):
        body = """
        all2text itself is installed with: python -m pip install .
        Source installs can invoke the external setup hook. Inspect or rerun setup with:
          python -m all2text setup --dry-run --profile full

        Interactive source installs can ask a yes/no setup question. Noninteractive installs never
        wait; use ALL2TEXT_SETUP_ASSUME_YES=1 for unattended setup. Built wheels cannot run arbitrary
        postinstall code. Common Windows commands:
          winget install Gyan.FFmpeg
          winget install UB-Mannheim.TesseractOCR
          winget install TheDocumentFoundation.LibreOffice

        The Unix file/getfacl tools are not expected on normal Windows installs. llama.cpp and
        model files are external. Start an OpenAI-compatible llama.cpp server and use all2text
        doctor to see the detected endpoint, or set the base_url in the TOML config.
        """
    elif name.startswith("darwin"):
        body = """
        all2text itself is installed with: python -m pip install .
        Source installs can invoke the external setup hook. Inspect or rerun setup with:
          python -m all2text setup --dry-run --profile full

        Interactive source installs can ask a yes/no setup question. Noninteractive installs never
        wait; use ALL2TEXT_SETUP_ASSUME_YES=1 for unattended setup. Built wheels cannot run arbitrary
        postinstall code. Common Homebrew commands:
          brew install ffmpeg tesseract libmagic libreoffice

        llama.cpp and model files are external. Start an OpenAI-compatible llama.cpp server and use
        all2text doctor to see what was found.
        """
    else:
        body = """
        all2text itself is installed with: python -m pip install .
        Source installs can invoke the external setup hook. Inspect or rerun setup with:
          python -m all2text setup --dry-run --profile full

        Interactive source installs can ask a yes/no setup question. Noninteractive installs never
        wait; use ALL2TEXT_SETUP_ASSUME_YES=1 for unattended setup. Install ffmpeg/ffprobe,
        Tesseract, LibreOffice, and llama.cpp using the setup report, your OS package manager, or
        vendor instructions. all2text will detect them automatically when they are on PATH, or you
        can configure absolute paths and endpoint URLs in the TOML config.
        """
    return textwrap.dedent(body).strip() + "\n"
