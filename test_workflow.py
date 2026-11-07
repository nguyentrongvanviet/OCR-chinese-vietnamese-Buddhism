"""CPU tests of persistence and recovery. No OCR weights or GPU are required."""

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

import zh_ocr_worker as worker


class WorkflowTests(unittest.TestCase):
    def test_resume_corruption_and_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "source.pdf"
            with pymupdf.open() as document:
                for number in range(3):
                    document.new_page().insert_text((50, 50), f"Source {number + 1}")
                document.save(pdf)
            args = argparse.Namespace(pdf=str(pdf), output=str(root / "results"),
                                      pages="all", pipeline_version="v1.6", dpi=200)
            calls, fail = [], {2}

            class FakeResult:
                def __init__(self, page):
                    self.page = page

                def save_to_json(self, save_path):
                    blocks = [] if self.page == 3 else [
                        {"block_content": f"釋迦如來。第{self.page}頁。", "block_order": 0},
                        {"block_content": "法師文鈔", "block_order": 1}]
                    Path(save_path).write_text(json.dumps({"res": {"parsing_res_list": blocks}},
                                                         ensure_ascii=False), encoding="utf-8")

            class FakePipeline:
                def __init__(self, **kwargs):
                    pass

                def predict(self, input):
                    page = int(Path(input).parent.name.split("_")[1])
                    calls.append(page)
                    if page in fail:
                        fail.remove(page)
                        raise RuntimeError("Simulated page interruption")
                    yield FakeResult(page)

            self.assertEqual(worker.run(args, FakePipeline), 1)
            output = Path(args.output)
            self.assertFalse((output / "han_ocr_full.txt").exists())
            self.assertEqual(calls, [1, 2, 3])
            self.assertEqual(worker.run(args, FakePipeline), 0)
            self.assertEqual(calls, [1, 2, 3, 2])

            def must_not_load(**kwargs):
                raise AssertionError("Should not reload the OCR model")

            self.assertEqual(worker.run(args, must_not_load), 0)
            text = (output / "han_ocr_full.txt").read_bytes().decode("utf-8")
            self.assertEqual(text.count("===== TRANG PDF "), 3)
            self.assertLess(text.index("第1頁"), text.index("第2頁"))
            self.assertIn("[OCR_RONG_CAN_KIEM_TRA_ANH_GOC]", text)
            self.assertEqual(json.loads((output / "summary.json").read_text())["empty_pages_need_review"], [3])
            (output / "pages/page_0001/text.txt").write_text("corrupted", encoding="utf-8")
            self.assertEqual(worker.run(args, FakePipeline), 0)
            self.assertEqual(calls[-1], 1)
            self.assertTrue((output / "pages/page_0001/text.txt").read_text().startswith("釋迦"))
            records = [json.loads(p.read_text()) for p in (output / "runs").glob("*.json")]
            self.assertEqual(len(records), 4)
            self.assertTrue(all("source" in record and "commit" in record["source"] for record in records))
            self.assertTrue((output / "environment-lock.txt").is_file())
            args.pipeline_version = "v1.5"
            with self.assertRaisesRegex(ValueError, "OUTPUT_NAME"):
                worker.run(args, FakePipeline)

    def test_invalid_page_ranges(self):
        self.assertEqual(worker.parse_pages("3,1-2,2", 3), [1, 2, 3])
        for value in ("0", "4", "3-1", "1,", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.parse_pages(value, 3)

    def test_bad_ocr_schema_is_not_silently_empty(self):
        for payload in ({}, {"res": {}}, {"parsing_res_list": ["bad"]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                worker.text_from_payload(payload)


if __name__ == "__main__":
    unittest.main()
