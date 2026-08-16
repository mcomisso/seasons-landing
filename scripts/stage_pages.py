"""Stage only allowlisted public files for GitHub Pages."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from provider_actions import verify_artifact_directory  # noqa: E402


PUBLIC_FILES = (
    ".nojekyll",
    "2phones.png",
    "App Store.svg",
    "CNAME",
    "Play Store.svg",
    "account-link.css",
    "account-link.js",
    "backgroundSite.png",
    "header.png",
    "horizontal.png",
    "index.html",
    "phone.png",
    "privacy.html",
    "raffleimage.jpg",
    "raffleprivacy.html",
    "raffleterms.html",
    "seasonslogo.png",
    "sitemap.xml",
    "terms.html",
)
PUBLIC_DIRECTORIES = (
    ".well-known",
    "family-invite",
    "recover-account",
    "replace-contact-email",
    "verify-contact-email",
)


def _validate_allowlisted_sources(repository_root: Path) -> None:
    for relative_path in PUBLIC_FILES:
        source = repository_root / relative_path
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"allowlisted public file is missing or unsafe: {relative_path}")
    for relative_path in PUBLIC_DIRECTORIES:
        source = repository_root / relative_path
        if not source.is_dir() or source.is_symlink():
            raise ValueError(f"allowlisted public directory is missing or unsafe: {relative_path}")
        for candidate in source.rglob("*"):
            if candidate.is_symlink():
                raise ValueError(f"allowlisted public directory contains a symlink: {candidate}")


def _copy_allowlisted_site(repository_root: Path, output: Path) -> None:
    for relative_path in PUBLIC_FILES:
        source = repository_root / relative_path
        destination = output / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for relative_path in PUBLIC_DIRECTORIES:
        source = repository_root / relative_path
        shutil.copytree(source, output / relative_path)


def stage(
    output: Path,
    provider_actions_artifact: Path,
    sealed_public_release: Mapping[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    if repository_root.is_symlink():
        raise ValueError("repository root cannot be a symlink")
    repository_root = repository_root.resolve()
    if repository_root == Path(repository_root.anchor):
        raise ValueError("repository root cannot be a filesystem root")
    if not repository_root.is_dir():
        raise ValueError("repository root must be a directory")
    if output.is_symlink():
        raise ValueError("_site cannot be a symlink")
    output = output.resolve()
    required_output = repository_root / "_site"
    if output != required_output:
        raise ValueError(f"output must be the repository-local staging directory: {required_output}")
    if provider_actions_artifact.is_symlink():
        raise ValueError("Provider Actions artifact cannot be a symlink")
    artifact = provider_actions_artifact.resolve()
    if artifact == output or output in artifact.parents:
        raise ValueError("Provider Actions artifact cannot come from the staging directory")
    verify_artifact_directory(artifact, sealed_public_release)
    _validate_allowlisted_sources(repository_root)
    if output.exists():
        if not output.is_dir():
            raise ValueError("_site must be a directory, not a file or symlink")
    temporary = Path(tempfile.mkdtemp(prefix=".site-stage-", dir=repository_root))
    backup: Path | None = None
    try:
        _copy_allowlisted_site(repository_root, temporary)
        shutil.copytree(artifact, temporary / "provider-actions")
        verify_artifact_directory(temporary / "provider-actions", sealed_public_release)
        if (temporary / "provider-actions" / "sitemap.xml").exists():
            raise ValueError("staging must not emit a static Provider Actions sitemap")
        if output.exists():
            backup = repository_root / f".site-backup-{uuid.uuid4().hex}"
            output.replace(backup)
        try:
            temporary.replace(output)
        except OSError:
            if backup is not None and backup.exists() and not output.exists():
                backup.replace(output)
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if backup is not None and backup.exists():
            if not output.exists():
                backup.replace(output)
            else:
                shutil.rmtree(backup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider-actions-artifact", type=Path, required=True)
    parser.add_argument("--sealed-release", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        sealed_release = json.loads(arguments.sealed_release.read_text(encoding="utf-8"))
        stage(
            arguments.output,
            arguments.provider_actions_artifact,
            sealed_release,
            repository_root=REPOSITORY_ROOT,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"stage-pages: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
