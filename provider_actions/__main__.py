"""Command-line adapters for rendering and scanning public artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import render, verify_artifact_directory


def _write_artifact(input_path: Path, output_path: Path) -> None:
    release = json.loads(input_path.read_text(encoding="utf-8"))
    artifact = render(release)
    output_parent = output_path.resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="provider-actions-", dir=output_parent))
    try:
        for relative_path, content in artifact.files.items():
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        verify_artifact_directory(temporary, release)
        if output_path.exists():
            if output_path.is_symlink() or not output_path.is_dir():
                raise ValueError("artifact output must be a directory, not a file or symlink")
            shutil.rmtree(output_path)
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render", help="render a sealed release")
    render_parser.add_argument("input", type=Path)
    render_parser.add_argument("output", type=Path)
    scan_parser = subparsers.add_parser("scan", help="scan a generated public artifact")
    scan_parser.add_argument("directory", type=Path)
    scan_parser.add_argument("sealed_release", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "render":
            _write_artifact(arguments.input, arguments.output)
        else:
            release = json.loads(arguments.sealed_release.read_text(encoding="utf-8"))
            verify_artifact_directory(arguments.directory, release)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"provider-actions: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
