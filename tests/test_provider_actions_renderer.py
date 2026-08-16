from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path

from provider_actions import render


FIXTURE = Path(__file__).parent / "fixtures" / "provider-actions-safe-release.json"


def reseal(release: dict) -> dict:
    payload = copy.deepcopy(release)
    payload.pop("releaseSha256", None)
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    payload["releaseSha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


class ProviderActionsRendererTests(unittest.TestCase):
    def test_safe_release_renders_a_deterministic_content_addressed_artifact(self) -> None:
        sealed_release = json.loads(FIXTURE.read_text(encoding="utf-8"))

        first = render(sealed_release)
        second = render(sealed_release)

        self.assertEqual(first.files, second.files)
        self.assertEqual(list(first.files), sorted(first.files))
        self.assertIn("manifest.json", first.files)

        manifest = json.loads(first.files["manifest.json"])
        self.assertEqual(manifest["releaseId"], "synthetic-safe-release")
        self.assertEqual(manifest["publishedGuideCount"], 0)
        self.assertEqual(manifest["responseCount"], 1)
        self.assertNotIn("generatedAt", manifest)
        self.assertFalse(any(path.endswith("sitemap.xml") for path in first.files))

        response_path = manifest["responses"][0]["path"]
        response = first.files[response_path]
        response_sha256 = hashlib.sha256(response).hexdigest()
        self.assertEqual(response_path, f"responses/{response_sha256}.html")
        self.assertEqual(manifest["responses"][0]["sha256"], response_sha256)

        html = response.decode("utf-8")
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        self.assertIn('<link rel="canonical" href="https://getseasons.app/provider-actions/cancel/8/GB/">', html)
        self.assertIn('<meta name="referrer" content="no-referrer">', html)
        self.assertIn('href="/provider-actions/assets/provider-actions-', html)
        self.assertIn("window.location.hash", html)
        self.assertIn("window.history.replaceState", html)
        self.assertIn("encodeURIComponent(context)", html)
        self.assertIn('id="seasons-return" href="https://getseasons.app/"', html)
        self.assertEqual(html.count("https://getseasons.app/provider-actions/return/#"), 1)
        self.assertNotIn("data-context", html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("console.", html)
        self.assertNotIn("account-link.js", html)
        self.assertNotIn("tailwind", html.lower())
        self.assertNotIn("hubspot", html.lower())
        self.assertNotIn("ahrefs", html.lower())

        first_script = html.index("<script>")
        self.assertLess(html.index('charset="utf-8"'), first_script)
        self.assertLess(html.index('name="viewport"'), first_script)
        self.assertLess(html.index('name="referrer"'), first_script)
        self.assertLess(html.index('http-equiv="content-security-policy"'), first_script)
        self.assertEqual(html.count("<script"), 1)

    def test_tampered_release_is_rejected_before_rendering(self) -> None:
        sealed_release = json.loads(FIXTURE.read_text(encoding="utf-8"))
        tampered = copy.deepcopy(sealed_release)
        tampered["pages"][0]["summary"] = "Tampered after sealing"

        with self.assertRaisesRegex(ValueError, "releaseSha256 does not match"):
            render(tampered)

    def test_unexpected_release_fields_are_rejected(self) -> None:
        sealed_release = json.loads(FIXTURE.read_text(encoding="utf-8"))
        sealed_release["privateRuntimeIndex"] = {"must": "not leak"}

        with self.assertRaisesRegex(ValueError, "unexpected field.*privateRuntimeIndex"):
            render(reseal(sealed_release))

    def test_safe_only_release_rejects_orphan_public_media(self) -> None:
        sealed_release = json.loads(FIXTURE.read_text(encoding="utf-8"))
        content = b"synthetic image bytes that must not be published"
        sealed_release["publicAssets"] = [
            {
                "assetId": "orphan-screenshot",
                "kind": "screenshot",
                "mediaType": "image/png",
                "sha256": hashlib.sha256(content).hexdigest(),
                "contentBase64": base64.b64encode(content).decode("ascii"),
            }
        ]

        with self.assertRaisesRegex(ValueError, "safe-only releases require empty publicAssets"):
            render(reseal(sealed_release))

    def test_contextual_return_uses_a_distinct_visible_label_only_when_fragment_is_present(self) -> None:
        sealed_release = json.loads(FIXTURE.read_text(encoding="utf-8"))
        sealed_release["pages"][0]["contextualSeasonsReturnLabel"] = "Return to cancellation confirmation"

        artifact = render(reseal(sealed_release))

        manifest = json.loads(artifact.files["manifest.json"])
        html = artifact.files[manifest["responses"][0]["path"]].decode("utf-8")
        self.assertIn('id="seasons-return" href="https://getseasons.app/">Open Seasons</a>', html)
        self.assertIn('returnAction.textContent = "Return to cancellation confirmation"', html)
        self.assertLess(html.index("if (!returnAction || !context) return"), html.index("returnAction.textContent"))


if __name__ == "__main__":
    unittest.main()
