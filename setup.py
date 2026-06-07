from __future__ import annotations

import os
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.install import install as _install

try:
    from setuptools.command.develop import develop as _develop
except Exception:  # pragma: no cover - depends on setuptools install mode
    _develop = None

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except Exception:  # pragma: no cover - wheel is in build-system requires
    _bdist_wheel = None


_HOOK_RAN = False


def _run_all2text_setup_hook(source: str) -> None:
    global _HOOK_RAN
    if _HOOK_RAN:
        return
    _HOOK_RAN = True
    root = Path(__file__).resolve().parent
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from all2text.install_hook import run_install_hook

        run_install_hook(source=source)
    except Exception as exc:
        print(f"all2text external setup hook warning: {type(exc).__name__}: {exc}", file=sys.stderr)
        if os.environ.get("ALL2TEXT_SETUP_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}:
            raise


class All2TextInstall(_install):
    def run(self) -> None:
        super().run()
        _run_all2text_setup_hook("setuptools_install")


cmdclass = {"install": All2TextInstall}


if _develop is not None:

    class All2TextDevelop(_develop):
        def run(self) -> None:
            super().run()
            _run_all2text_setup_hook("setuptools_develop")

    cmdclass["develop"] = All2TextDevelop


if _bdist_wheel is not None:

    class All2TextBdistWheel(_bdist_wheel):
        def run(self) -> None:
            super().run()
            _run_all2text_setup_hook("bdist_wheel")

    cmdclass["bdist_wheel"] = All2TextBdistWheel


setup(cmdclass=cmdclass)
