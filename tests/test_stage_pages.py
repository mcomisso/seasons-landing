from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from provider_actions import render
from scripts.stage_pages import PUBLIC_DIRECTORIES, PUBLIC_FILES, stage


class StagePagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "landing"
        self.repository.mkdir()
        for relative_path in PUBLIC_FILES:
            destination = self.repository / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(f"public file: {relative_path}\n".encode("utf-8"))
        for relative_path in PUBLIC_DIRECTORIES:
            destination = self.repository / relative_path / "fixture.txt"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(f"public directory: {relative_path}\n".encode("utf-8"))
        (self.repository / "AGENTS.md").write_text("must not publish\n", encoding="utf-8")
        self.release = {
            "schemaVersion": "1",
            "releaseId": "test-safe-baseline",
            "canonicalOrigin": "https://getseasons.app",
            "templateContractVersion": "1",
            "pages": [],
            "credits": {
                "tmdbNotice": "This product uses the TMDB API but is not endorsed or certified by TMDB.",
                "justWatchAttribution": "Watch-provider availability data is attributed to JustWatch.",
            },
            "publicAssets": [],
        }
        canonical_release = json.dumps(
            self.release, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        self.release["releaseSha256"] = hashlib.sha256(canonical_release).hexdigest()
        self.artifact = self.root / "artifact"
        self.artifact.mkdir()
        for relative_path, content in render(self.release).files.items():
            destination = self.artifact / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_stage_replaces_only_site_with_the_exact_public_allowlist(self) -> None:
        output = self.repository / "_site"
        output.mkdir()
        (output / "stale.txt").write_text("stale\n", encoding="utf-8")

        stage(output, self.artifact, self.release, repository_root=self.repository)

        expected = set(PUBLIC_FILES) | {
            f"provider-actions/{path}" for path in render(self.release).files
        }
        for relative_path in PUBLIC_DIRECTORIES:
            expected.add(f"{relative_path}/fixture.txt")
        actual = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, expected)
        self.assertFalse((output / "stale.txt").exists())
        self.assertFalse((output / "AGENTS.md").exists())
        for relative_path in PUBLIC_FILES:
            self.assertEqual((output / relative_path).read_bytes(), (self.repository / relative_path).read_bytes())

    def test_account_deletion_request_page_is_public(self) -> None:
        self.assertIn("delete-account", PUBLIC_DIRECTORIES)

    def test_unsafe_output_is_rejected_without_touching_it(self) -> None:
        unsafe_output = self.root / "not-the-site"
        unsafe_output.mkdir()
        sentinel = unsafe_output / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "repository-local staging directory"):
            stage(unsafe_output, self.artifact, self.release, repository_root=self.repository)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_symlinked_artifact_is_rejected_without_replacing_the_site(self) -> None:
        output = self.repository / "_site"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        artifact_link = self.root / "artifact-link"
        artifact_link.symlink_to(self.artifact, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "artifact cannot be a symlink"):
            stage(output, artifact_link, self.release, repository_root=self.repository)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_unsafe_allowlisted_symlink_does_not_replace_the_existing_site(self) -> None:
        output = self.repository / "_site"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        unsafe_source = self.repository / PUBLIC_FILES[0]
        unsafe_source.unlink()
        unsafe_source.symlink_to(self.repository / "AGENTS.md")

        with self.assertRaisesRegex(ValueError, "allowlisted public file is missing or unsafe"):
            stage(output, self.artifact, self.release, repository_root=self.repository)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
