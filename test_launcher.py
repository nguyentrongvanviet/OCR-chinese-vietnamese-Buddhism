"""Exercise the CLI-to-artifact path without a GPU or DagsHub credentials."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from build_notebook import build
from export_results import validate_bundle
import run_ocr
import zh_ocr_worker as worker


class LauncherTests(unittest.TestCase):
    def test_cli_produces_complete_zip_without_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf, output = root / "source.pdf", root / "results"
            with pymupdf.open() as document:
                document.new_page().insert_text((50, 50), "Test")
                document.save(pdf)

            class Result:
                def save_to_json(self, save_path):
                    Path(save_path).write_text(json.dumps({"parsing_res_list": [
                        {"block_content": "印光法師文鈔。"}]}, ensure_ascii=False), encoding="utf-8")

            class Pipeline:
                def __init__(self, **kwargs):
                    pass
                def predict(self, input, **kwargs):
                    yield Result()

            actual_run = worker.run
            argv = ["run_ocr.py", "--pdf", str(pdf), "--output", str(output),
                    "--pages", "all", "--work-dir", str(root / "runtime")]
            with patch("sys.argv", argv), patch.object(worker, "run", side_effect=lambda args: actual_run(args, Pipeline)), \
                    patch("export_results.upload_export") as upload:
                self.assertEqual(run_ocr.main(), 0)
                upload.assert_not_called()
            self.assertIn("印光", (output / "han_ocr_full.txt").read_text(encoding="utf-8"))
            bundle = Path(json.loads((output / "latest_export.json").read_text())["path"])
            validate_bundle(bundle)
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertTrue(manifest["complete_book"])
            self.assertEqual(manifest["done_pages"], [1])
            self.assertFalse(manifest["quality_reviewed"])

    def test_notebook_syntax_and_generated_file_match(self):
        generated = build("https://github.com/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism.git")
        committed = json.loads((Path(__file__).parent / "OCR_Han_Colab.ipynb").read_text())
        self.assertEqual(generated, committed)
        for cell in generated["cells"]:
            if cell["cell_type"] == "code":
                ast.parse("".join(cell["source"]))
                self.assertEqual(cell["outputs"], [])


if __name__ == "__main__":
    unittest.main()
