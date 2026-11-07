"""OCR Chinese PDF pages with PaddleOCR-VL; retain raw results and resume safely.

The Colab notebook clones the repository and invokes run_ocr.py.
No translation, alignment, character conversion, or duplex restoration is performed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid


FORMAT_VERSION = 2


def source_revision():
    try:
        root = Path(__file__).resolve().parent
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  text=True, capture_output=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                               text=True, capture_output=True, check=True).stdout.strip()
        return {"commit": revision, "working_tree_dirty": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "working_tree_dirty": None}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def parse_pages(specification, count):
    if specification.strip().lower() == "all":
        return list(range(1, count + 1))
    pages = set()
    for part in specification.split(","):
        part = part.strip()
        if not part:
            raise ValueError("Danh sách trang chứa mục rỗng.")
        if "-" in part:
            first, last = map(int, part.split("-"))
            if first > last:
                raise ValueError("Trang bắt đầu phải nhỏ hơn hoặc bằng trang kết thúc.")
            pages.update(range(first, last + 1))
        else:
            pages.add(int(part))
    if not pages or min(pages) < 1 or max(pages) > count:
        raise ValueError(f"Chỉ được chọn các trang PDF trong khoảng 1–{count}.")
    return sorted(pages)


def blocks_from_payload(payload):
    root = payload
    if isinstance(root, dict) and isinstance(root.get("res"), dict):
        root = root["res"]
    if not isinstance(root, dict) or not isinstance(root.get("parsing_res_list"), list):
        raise ValueError("JSON OCR không có parsing_res_list; giữ file thô để kiểm tra API.")
    blocks = root["parsing_res_list"]
    if not all(isinstance(block, dict) for block in blocks):
        raise ValueError("Cấu trúc block OCR không hợp lệ.")
    return blocks


def text_from_payload(payload):
    # The documented list order is the pipeline's reading order. Do not re-sort
    # vertical Chinese by the conventional horizontal (y, x) ordering.
    parts = []
    for block in blocks_from_payload(payload):
        content = block.get("block_content")
        if content is None:
            continue
        if not isinstance(content, str):
            raise ValueError("block_content không phải chuỗi văn bản.")
        if content.strip():
            parts.append(content)
    return "\n\n".join(parts)


def completed_status(directory, run_id):
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        if status.get("run_id") != run_id or status.get("status") != "done":
            return None
        for filename in ("source.png", "raw.json", "text.txt"):
            if sha256(directory / filename) != status["sha256"][filename]:
                return None
        text = (directory / "text.txt").read_text(encoding="utf-8")
        payload = json.loads((directory / "raw.json").read_text(encoding="utf-8"))
        if text != text_from_payload(payload):
            return None
        return status
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_page_image(document, number, output, dpi):
    from PIL import Image
    import pymupdf

    page = document.load_page(number - 1)
    images = page.get_images(full=True)
    info = page.get_image_info(xrefs=True)
    # This project's PDF contains one full-page scan per page. Only take the
    # native image when its placement has no rotation, reflection, or cropping.
    native = False
    if len(images) == 1 and len(info) == 1 and page.rotation == 0:
        transform = info[0]["transform"]
        bounds = pymupdf.Rect(info[0]["bbox"])
        coverage = bounds & page.rect
        native = (transform[0] > 0 and transform[3] > 0
                  and abs(transform[1]) < 1e-4 and abs(transform[2]) < 1e-4
                  and abs(coverage.get_area() - page.rect.get_area()) < 1
                  and abs(bounds.get_area() - page.rect.get_area()) < 1)
    if native:
        image = document.extract_image(images[0][0])
        with Image.open(io.BytesIO(image["image"])) as scan:
            scan.convert("RGB").save(output)
        return "native_scan"
    page.get_pixmap(dpi=dpi, alpha=False).save(output)
    return f"rendered_{dpi}dpi"


def aggregate(output, count, run_id):
    finished, empty, failed, missing = [], [], [], []
    chunks = []
    for number in range(1, count + 1):
        directory = output / "pages" / f"page_{number:04d}"
        status = completed_status(directory, run_id)
        chunks.append(f"===== TRANG PDF {number:04d} =====\n")
        if status is None:
            missing.append(number)
            try:
                current = json.loads((directory / "status.json").read_text(encoding="utf-8"))
                if current.get("run_id") == run_id and current.get("status") == "failed":
                    failed.append(number)
            except (OSError, ValueError):
                pass
            chunks.append("[CHUA_CO_KET_QUA_OCR]\n\n")
            continue
        finished.append(number)
        text = (directory / "text.txt").read_text(encoding="utf-8")
        if not text.strip():
            empty.append(number)
            chunks.append("[OCR_RONG_CAN_KIEM_TRA_ANH_GOC]\n\n")
        else:
            chunks.append(text + "\n\n")
    combined = "".join(chunks)
    write_text(output / "han_ocr_partial.txt", combined)
    full = output / "han_ocr_full.txt"
    if not missing:
        write_text(full, combined)
    elif full.exists():
        full.unlink()  # Never leave a stale full-file export after a broken checkpoint.
    summary = {
        "run_id": run_id, "total_pdf_pages": count,
        "done_pages": finished, "missing_pages": missing,
        "failed_pages": failed, "empty_pages_need_review": empty,
        "complete_processing": not missing,
        "human_verified": False,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output / "summary.json", summary)
    notes = ["Đây là OCR thô, chưa được kiểm chứng thủ công.",
             "Chưa khử chữ xuyên mặt sau; chưa tự sửa chữ hoặc chuyển sang giản thể.",
             "Thứ tự block do mô hình dự đoán; cần đối chiếu các cột dọc với ảnh gốc.",
             "Trang chưa có kết quả: " + ", ".join(map(str, missing)),
             "Trang chạy lỗi: " + ", ".join(map(str, failed)),
             "Trang OCR rỗng, cần xem ảnh: " + ", ".join(map(str, empty))]
    write_text(output / "NOTE.txt", "\n".join(notes) + "\n")
    return summary


def run(args, pipeline_factory=None):
    import pymupdf

    pdf = Path(args.pdf).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    with pymupdf.open(pdf) as document:
        if document.needs_pass:
            raise ValueError("PDF yêu cầu mật khẩu.")
        count = len(document)
        selected = parse_pages(args.pages, count)
        configuration = {
            "format_version": FORMAT_VERSION,
            "worker_sha256": sha256(Path(__file__)),
            "pdf_sha256": sha256(pdf), "page_count": count,
            "pipeline_version": args.pipeline_version, "fallback_dpi": args.dpi,
            "paddleocr": package_version("paddleocr"),
            "paddlex": package_version("paddlex"),
            "paddlepaddle_gpu": package_version("paddlepaddle-gpu"),
            "pymupdf": package_version("PyMuPDF"),
            "pillow": package_version("Pillow"),
            "reading_order": "pipeline_parsing_res_list",
            "preprocessing": "original; orientation and unwarping disabled",
            "text_policy": "all nonempty block contents; no character conversion",
        }
        run_id = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
        configuration["run_id"] = run_id
        config_file = output / "config.json"
        if config_file.exists():
            previous = json.loads(config_file.read_text(encoding="utf-8"))
            if previous != configuration:
                raise ValueError("Nguồn, mô hình hoặc phiên bản đã đổi. Chọn OUTPUT_NAME mới để tránh trộn kết quả.")
        else:
            if output.exists() and any(output.iterdir()):
                raise ValueError("Thư mục đầu ra có dữ liệu nhưng thiếu config.json. Chọn thư mục mới.")
            write_json(config_file, configuration)

        todo = [n for n in selected if not completed_status(output / "pages" / f"page_{n:04d}", run_id)]
        print(f"PDF: {count} trang. Đã chọn: {len(selected)}. Cần chạy: {len(todo)}.", flush=True)
        failures = []
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        record_path = output / "runs" / f"{stamp}_{uuid.uuid4().hex[:8]}.json"
        record = {"run_id": run_id, "source": source_revision(), "selected_pages": selected,
                  "state": "running", "started_at_utc": datetime.now(timezone.utc).isoformat()}
        write_json(record_path, record)
        versions = sorted(f"{dist.metadata['Name']}=={dist.version}"
                          for dist in importlib.metadata.distributions() if dist.metadata.get("Name"))
        write_text(output / "environment-lock.txt", "\n".join(versions) + "\n")
        try:
            if todo:
                if pipeline_factory is None:
                    from paddleocr import PaddleOCRVL
                    pipeline_factory = PaddleOCRVL
                pipeline = pipeline_factory(
                    pipeline_version=args.pipeline_version, device="gpu:0",
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_layout_detection=True,
                )
                for number in todo:
                    directory = output / "pages" / f"page_{number:04d}"
                    directory.mkdir(parents=True, exist_ok=True)
                    started = time.monotonic()
                    try:
                        source = directory / "source.png"
                        image_mode = save_page_image(document, number, source, args.dpi)
                        results = iter(pipeline.predict(input=str(source)))
                        result = next(results, None)
                        if result is None or next(results, None) is not None:
                            raise ValueError("Mỗi ảnh trang phải có đúng một kết quả OCR.")
                        raw_temp = directory / "raw.pending.json"
                        result.save_to_json(save_path=str(raw_temp))
                        payload = json.loads(raw_temp.read_text(encoding="utf-8"))
                        text = text_from_payload(payload)
                        raw_temp.replace(directory / "raw.json")
                        write_text(directory / "text.txt", text)
                        status = {
                            "run_id": run_id, "status": "done", "pdf_page": number,
                            "characters": len(text), "empty_needs_review": not text.strip(),
                            "image_mode": image_mode,
                            "seconds": round(time.monotonic() - started, 2),
                            "sha256": {name: sha256(directory / name)
                                       for name in ("source.png", "raw.json", "text.txt")},
                        }
                        write_json(directory / "status.json", status)
                        print(f"Trang {number:04d}: {len(text)} ký tự, {status['seconds']} giây"
                              + (" — OCR RỖNG, CẦN KIỂM TRA" if not text.strip() else ""), flush=True)
                    except Exception as error:
                        failures.append(number)
                        write_json(directory / "status.json", {
                            "run_id": run_id, "status": "failed", "pdf_page": number,
                            "error": repr(error), "traceback": traceback.format_exc(),
                        })
                        print(f"LỖI trang {number}: {error}", flush=True)
                        # GPU OOM may leave the process unhealthy. Resume in a fresh
                        # runtime instead of failing every remaining page.
                        if any(term in str(error).lower() for term in ("out of memory", "resourceexhausted")):
                            break
            record["state"] = "failed" if failures else "finished"
        except BaseException as error:
            record["state"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
            record["error"] = repr(error)
            raise
        finally:
            summary = aggregate(output, count, run_id)
            record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            record["done_pages"] = summary["done_pages"]
            record["failed_pages_this_attempt"] = failures
            write_json(record_path, record)
            print(f"Đã lưu {len(summary['done_pages'])}/{count} trang; "
                  f"còn thiếu {len(summary['missing_pages'])}; "
                  f"OCR rỗng {len(summary['empty_pages_need_review'])}. Đầu ra: {output}", flush=True)
        return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pages", default="3,4,5", help="all, 3,4,5 hoặc 1-25")
    parser.add_argument("--pipeline-version", default="v1.6", choices=("v1.6", "v1.5", "v1"))
    parser.add_argument("--dpi", type=int, default=200, help="Chỉ dùng khi cần render thay vì lấy ảnh gốc.")
    args = parser.parse_args()
    if not 72 <= args.dpi <= 600:
        parser.error("DPI phải trong khoảng 72–600.")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
