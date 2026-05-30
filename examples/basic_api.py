from __future__ import annotations

from all2text import run


def main() -> None:
    manifest = run("sample_source", "sample_output")
    print(manifest["summary"])


if __name__ == "__main__":
    main()

