"""Validate export integrity and remote completion semantics without network access."""

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

from export_results import make_export, validate_bundle
import zh_ocr_worker as worker


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

    def test_partial_export_retains_scope_and_utf8(self):
        bundle = make_export(self.output, "all")
        validate_bundle(bundle)
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual(manifest["missing_pages"], [2])
        self.assertFalse(manifest["complete_scope"])
        self.assertFalse(manifest["complete_book"])
        self.assertFalse(manifest["quality_reviewed"])
        self.assertIn("釋迦", (bundle / "han.txt").read_text())
        self.assertFalse(any(p.suffix == ".png" for p in bundle.rglob("*")))

    def test_corrupted_export_is_rejected(self):
        bundle = make_export(self.output, "1")
        (bundle / "han.txt").write_text("damaged", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
