"""Validate export integrity and remote completion semantics without network access."""

import argparse
import io
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

from export_results import make_export, upload_export, validate_bundle
import zh_ocr_worker as worker


class NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.fail_key = None

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NotFound()
        data, metadata = self.objects[Key]
        return {"ContentLength": len(data), "Metadata": metadata}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NotFound()
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def upload_file(self, Filename, Bucket, Key, ExtraArgs):
        if self.fail_key and Key.endswith(self.fail_key):
            raise OSError("Simulated upload interruption")
        self.objects[Key] = (Path(Filename).read_bytes(), ExtraArgs["Metadata"])
        self.writes.append(Key)

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = (Body, {})
        self.writes.append(Key)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "ocr"
        pdf = self.root / "input.pdf"
        with pymupdf.open() as document:
            document.new_page().insert_text((30, 50), "Test page one")
            document.new_page().insert_text((30, 50), "Test page two")
            document.save(pdf)

        class Result:
            def save_to_json(self, save_path):
                Path(save_path).write_text(json.dumps({"res": {"parsing_res_list": [
                    {"block_content": "釋迦如來。", "block_bbox": [1, 2, 3, 4]}]}}, ensure_ascii=False), encoding="utf-8")

        class Pipeline:
            def __init__(self, **kwargs):
                pass

            def predict(self, input, **kwargs):
                yield Result()

        args = argparse.Namespace(pdf=str(pdf), output=str(self.output), pages="1",
                                  pipeline_version="v1.6", dpi=200)
        worker.run(args, Pipeline)

    def tearDown(self):
        self.temporary.cleanup()

    def test_partial_export_and_success_last(self):
        bundle = make_export(self.output, "all")
        validate_bundle(bundle)
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual(manifest["missing_pages"], [2])
        self.assertFalse(manifest["complete_scope"])
        self.assertFalse(manifest["complete_book"])
        self.assertFalse(manifest["quality_reviewed"])
        self.assertIn("釋迦", (bundle / "han.txt").read_text())
        self.assertFalse(any(p.suffix == ".png" for p in bundle.rglob("*")))
        client = FakeStorage()
        receipt = upload_export(bundle, "team/ocr-data", client=client, attempts=1)
        self.assertTrue(client.writes[-1].endswith("/_SUCCESS.json"))
        self.assertFalse(receipt["complete_book"])
        before = list(client.writes)
        self.assertEqual(upload_export(bundle, "team/ocr-data", client=client), receipt)
        self.assertEqual(client.writes, before)

    def test_upload_interruption_retries_without_ocr(self):
        bundle = make_export(self.output, "1")
        client = FakeStorage()
        client.fail_key = "pages.jsonl"
        with self.assertRaises(OSError):
            upload_export(bundle, "team/ocr-data", client=client, attempts=1)
        self.assertFalse(any(key.endswith("/_SUCCESS.json") for key in client.objects))
        self.assertTrue((bundle / "upload_pending.json").is_file())
        self.assertTrue((bundle / "bundle.zip").is_file())
        completed_writes = list(client.writes)
        client.fail_key = None
        upload_export(bundle, "team/ocr-data", client=client, attempts=1)
        for key in completed_writes:
            self.assertEqual(client.writes.count(key), 1)
        self.assertTrue(client.writes[-1].endswith("/_SUCCESS.json"))

    def test_corrupted_export_never_publishes_marker(self):
        bundle = make_export(self.output, "1")
        (bundle / "han.txt").write_text("damaged", encoding="utf-8")
        client = FakeStorage()
        with self.assertRaises(ValueError):
            upload_export(bundle, "team/ocr-data", client=client, attempts=1)
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
