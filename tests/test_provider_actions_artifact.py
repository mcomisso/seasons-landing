from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from provider_actions import render, verify_artifact_directory


FIXTURE = Path(__file__).parent / "fixtures" / "provider-actions-safe-release.json"


def write_files(directory: Path, files: dict[str, bytes]) -> None:
    for relative_path, content in files.items():
        destination = directory / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


class ProviderActionsArtifactTests(unittest.TestCase):
    def test_direct_scan_requires_exact_bytes_from_the_pinned_render(self) -> None:
        release = json.loads(FIXTURE.read_text(encoding="utf-8"))
        expected = render(release)
        attacker_files = dict(expected.files)
        manifest = json.loads(attacker_files["manifest.json"])
        old_path = manifest["responses"][0]["path"]
        content = attacker_files.pop(old_path).replace(
            b"<body>", b'<body onclick="window.alert(1)">'
        )
        content_sha256 = hashlib.sha256(content).hexdigest()
        new_path = f"responses/{content_sha256}.html"
        attacker_files[new_path] = content
        for entry in manifest["files"]:
            if entry["path"] == old_path:
                entry.update(path=new_path, sha256=content_sha256, size=len(content))
        manifest["files"].sort(key=lambda entry: entry["path"])
        manifest["responses"][0].update(path=new_path, sha256=content_sha256)
        attacker_files["manifest.json"] = (
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact_directory = Path(temporary_directory)
            write_files(artifact_directory, attacker_files)

            with self.assertRaisesRegex(ValueError, "does not exactly match the sealed render"):
                verify_artifact_directory(artifact_directory, release)


if __name__ == "__main__":
    unittest.main()
