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

        External tools are not installed by pip. all2text will auto-detect them if present.
        Common Debian/Ubuntu packages:
          sudo apt-get update
          sudo apt-get install -y ffmpeg tesseract-ocr libmagic1 file acl libreoffice

        llama.cpp and model files are intentionally external. Start an OpenAI-compatible llama.cpp
        server, then all2text will probe configured/common local endpoints such as 127.0.0.1:14829
        for text and 127.0.0.1:14830 for vision. Use all2text doctor to see what was found.
        """
    elif name.startswith("windows"):
        body = """
        all2text itself is installed with: python -m pip install .

        External tools are not installed by pip. all2text will auto-detect them if present on PATH
        or if configured explicitly. Common Windows options:
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

        External tools are not installed by pip. all2text will auto-detect them if present.
        Common Homebrew packages:
          brew install ffmpeg tesseract libmagic libreoffice

        llama.cpp and model files are external. Start an OpenAI-compatible llama.cpp server and use
        all2text doctor to see what was found.
        """
    else:
        body = """
        all2text itself is installed with: python -m pip install .

        External tools are not installed by pip. Install ffmpeg/ffprobe, Tesseract, LibreOffice,
        and llama.cpp using your OS package manager or vendor instructions. all2text will detect
        them automatically when they are on PATH, or you can configure absolute paths and endpoint
        URLs in the TOML config.
        """
    return textwrap.dedent(body).strip() + "\n"
