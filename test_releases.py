"""Test versioned naming, interrupted uploads and publish-after-verification."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request

from github_release import GitHubError, SafeRedirect, product_slug, publish_txt


class FakeGitHub:
    def __init__(self):
        self.releases = []
        self.assets = {}
        self.uploaded = []
        self.published = []
        self.fail_manifest = False
        self.corrupt = False
        self.race = False

    def list_releases(self, repo):
        return list(self.releases)

    def create_release(self, repo, payload):
        release = dict(payload, id=len(self.releases) + 1,
                       upload_url="https://uploads.github.com/upload{?name}",
                       html_url="https://github.com/" + repo + "/releases/tag/" + payload["tag_name"])
        self.releases.append(release)
        if self.race:
            self.race = False
            release["body"] = "Another publisher owns this version"
            raise GitHubError(422)
        return release

    def list_assets(self, repo, release_id):
        return [item[0] for item in self.assets.values() if item[0]["release_id"] == release_id]

    def upload_asset(self, release, file):
        if self.fail_manifest and file.name.endswith(".manifest.json"):
            raise OSError("Interrupted upload")
        item = {"id": len(self.assets) + 1, "name": file.name, "release_id": release["id"],
                "browser_download_url": "https://github.com/download/untagged/" + file.name}
        self.assets[item["id"]] = (item, file.read_bytes())
        self.uploaded.append(file.name)
        return item

    def download_asset(self, repo, asset_id):
        return b"corrupt" if self.corrupt else self.assets[asset_id][1]

    def publish(self, repo, release_id):
        release = self.get_release(repo, release_id)
        release["draft"] = False
        for item, _ in self.assets.values():
            if item["release_id"] == release_id:
                item["browser_download_url"] = item["browser_download_url"].replace("/untagged/", "/" + release["tag_name"] + "/")
        self.published.append(release_id)
        return release

    def get_release(self, repo, release_id):
        return next(item for item in self.releases if item["id"] == release_id)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.txt = self.root / "han.txt"
        self.txt.write_text("===== TRANG PDF 0003 =====\n印光法師文鈔。\n", encoding="utf-8")
        self.client = FakeGitHub()
        self.options = dict(repo="viet/ocr", product="Ấn Quang Văn Sao Zh", client=self.client,
                            state_dir=self.root / "state", metadata={"scope_pages": [3], "complete_book": False},
                            now=datetime(2026, 11, 8, 3, 4, 5, tzinfo=timezone.utc))

    def tearDown(self):
        self.temp.cleanup()

    def test_name_next_remote_version_and_vietnam_time(self):
        self.client.create_release("viet/ocr", {"tag_name": "ocr-viet-an-quang-van-sao-zh-v0007",
                                               "body": "old", "draft": False})
        receipt = publish_txt(self.txt, **self.options)
        self.assertEqual(receipt["version"], 8)
        self.assertNotIn("/untagged/", receipt["txt_url"])
        self.assertIn("v0008/", receipt["txt_url"])
        self.assertEqual(receipt["txt_filename"], "viet_an-quang-van-sao-zh_v0008_100405_2026-11-08.txt")
        self.assertEqual(self.client.assets[1][1], self.txt.read_bytes())
        self.assertEqual(len(self.client.uploaded), 3)
        self.assertEqual(self.client.published, [2])
        self.assertFalse(self.client.releases[-1]["draft"])
        self.assertTrue(self.client.releases[-1]["prerelease"])

    def test_retry_reuses_version_timestamp_and_verified_assets(self):
        self.client.fail_manifest = True
        with self.assertRaises(OSError):
            publish_txt(self.txt, **self.options)
        self.assertEqual(self.client.published, [])
        self.assertTrue((self.root / "state/upload_pending.json").exists())
        self.client.fail_manifest = False
        self.options["now"] = datetime(2027, 1, 1, tzinfo=timezone.utc)
        receipt = publish_txt(self.txt, **self.options)
        self.assertEqual(receipt["txt_filename"], "viet_an-quang-van-sao-zh_v0001_100405_2026-11-08.txt")
        self.assertEqual(len(self.client.uploaded), 3)
        self.assertFalse((self.root / "state/upload_pending.json").exists())
        before = list(self.client.uploaded)
        self.assertEqual(publish_txt(self.txt, **self.options), receipt)
        self.assertEqual(self.client.uploaded, before)
        self.assertEqual(self.client.published, [1])

    def test_version_race_allocates_new_number_without_overwriting(self):
        self.client.race = True
        receipt = publish_txt(self.txt, **self.options)
        self.assertEqual(receipt["version"], 2)
        self.assertEqual(self.client.releases[0]["body"], "Another publisher owns this version")

    def test_bad_remote_hash_keeps_draft(self):
        self.client.corrupt = True
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            publish_txt(self.txt, **self.options)
        self.assertEqual(self.client.published, [])
        self.assertTrue(self.client.releases[0]["draft"])

    def test_changed_txt_cannot_replace_existing_plan(self):
        publish_txt(self.txt, **self.options)
        self.txt.write_text("別的內容", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "đã đổi"):
            publish_txt(self.txt, **self.options)
        self.assertEqual(len(self.client.releases), 1)

    def test_explicit_existing_version_and_invalid_number_rejected(self):
        publish_txt(self.txt, **self.options)
        self.options["state_dir"] = self.root / "another_state"
        with self.assertRaisesRegex(ValueError, "đã có"):
            publish_txt(self.txt, version="1", **self.options)
        with self.assertRaises(ValueError):
            publish_txt(self.txt, version="0", **self.options)
        self.assertEqual(product_slug("Ấn Quang Văn Sao"), "an-quang-van-sao")

    def test_redirect_does_not_forward_token_to_asset_host(self):
        request = Request("https://api.github.com/asset", headers={"Authorization": "Bearer secret"})
        redirected = SafeRedirect().redirect_request(request, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/asset")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(request, None, 302, "Found", {}, "http://example.org")


if __name__ == "__main__":
    unittest.main()
