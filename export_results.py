"""Package validated OCR checkpoints for local use or GitHub Releases.

Never includes the source PDF, credentials or arbitrary files from the output folder.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import uuid
import zipfile

from zh_ocr_worker import completed_status, parse_pages, sha256, write_json, write_text


def make_export(output, pages="all", include_images=False):
    output = Path(output).resolve()
    config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    selected = parse_pages(pages, config["page_count"])
    export_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10]
    bundle = output / "exports" / export_id
    bundle.mkdir(parents=True)
    rows, chunks, done, missing, empty = [], [], [], [], []
    for number in selected:
        folder = output / "pages" / f"page_{number:04d}"
        status = completed_status(folder, config["run_id"])
        chunks.append(f"===== TRANG PDF {number:04d} =====\n")
        if status is None:
            missing.append(number)
            rows.append({"pdf_page": number, "status": "missing", "text": None})
            chunks.append("[CHUA_CO_KET_QUA_OCR]\n\n")
            continue
        done.append(number)
        text = (folder / "text.txt").read_text(encoding="utf-8")
        raw = json.loads((folder / "raw.json").read_text(encoding="utf-8"))
        if not text.strip():
            empty.append(number)
        rows.append({"pdf_page": number, "status": "empty_needs_review" if not text.strip() else "done",
                     "text": text, "raw": raw})
        chunks.append((text if text.strip() else "[OCR_RONG_CAN_KIEM_TRA_ANH_GOC]") + "\n\n")
        page_out = bundle / "pages" / f"page_{number:04d}"
        page_out.mkdir(parents=True)
        for name in ("raw.json", "text.txt", "status.json"):
            (page_out / name).write_bytes((folder / name).read_bytes())
        if include_images:
            (page_out / "source.png").write_bytes((folder / "source.png").read_bytes())

    manifest = {
        "format_version": 1, "export_id": export_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_pdf_sha256": config["pdf_sha256"], "ocr_config": config,
        "scope_pages": selected, "done_pages": done, "missing_pages": missing,
        "empty_pages_need_review": empty, "complete_scope": not missing,
        "complete_book": len(done) == config["page_count"], "quality_reviewed": False,
        "source_images_included": include_images,
    }
    write_text(bundle / "han.txt", "".join(chunks))
    write_text(bundle / "pages.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    write_json(bundle / "manifest.json", manifest)
    write_text(bundle / "NOTE.txt", "\n".join([
        "OCR thô; chưa kiểm chứng chất lượng chữ hoặc khử lem theo cặp.",
        "Phạm vi trang PDF: " + ", ".join(map(str, selected)),
        "Trang thiếu: " + ", ".join(map(str, missing)),
        "Trang OCR rỗng, cần kiểm tra ảnh: " + ", ".join(map(str, empty)),
    ]) + "\n")
    if (output / "environment-lock.txt").is_file():
        write_text(bundle / "environment-lock.txt", (output / "environment-lock.txt").read_text(encoding="utf-8"))
    payload = sorted(path for path in bundle.rglob("*") if path.is_file())
    checksums = {path.relative_to(bundle).as_posix(): sha256(path) for path in payload}
    write_text(bundle / "checksums.sha256", "".join(f"{digest}  {name}\n" for name, digest in checksums.items()))
    with zipfile.ZipFile(bundle / "bundle.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file() and path.name != "bundle.zip":
                archive.write(path, path.relative_to(bundle).as_posix())
    write_json(output / "latest_export.json", {"path": str(bundle), "export_id": export_id,
                                              "complete_scope": not missing, "complete_book": manifest["complete_book"]})
    return bundle


def validate_bundle(bundle):
    bundle = Path(bundle).resolve()
    checksums = {}
    for line in (bundle / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Đường dẫn không hợp lệ trong checksums.sha256.")
        path = bundle / name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"File trong gói xuất bị thiếu hoặc hỏng: {name}")
        checksums[name] = digest
    if not {"manifest.json", "han.txt", "pages.jsonl", "NOTE.txt"}.issubset(checksums):
        raise ValueError("Gói xuất thiếu các file bắt buộc.")
    with zipfile.ZipFile(bundle / "bundle.zip") as archive:
        expected = set(checksums) | {"checksums.sha256"}
        if set(archive.namelist()) != expected:
            raise ValueError("Nội dung ZIP không khớp gói xuất.")
        for name, digest in checksums.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Nội dung ZIP sai checksum: {name}")
        if archive.read("checksums.sha256") != (bundle / "checksums.sha256").read_bytes():
            raise ValueError("Checksum list trong ZIP không khớp.")
    checksums["checksums.sha256"] = sha256(bundle / "checksums.sha256")
    checksums["bundle.zip"] = sha256(bundle / "bundle.zip")
    return checksums



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--output", type=Path, help="Thư mục checkpoint để tạo gói xuất.")
    source.add_argument("--bundle", type=Path, help="Gói đã tạo; thử upload lại mà không OCR lại.")
    parser.add_argument("--pages", default="all")
    parser.add_argument("--include-images", action="store_true")
    parser.add_argument("--github-repo", help="owner/repo; bỏ trống để chỉ đóng gói trên Drive.")
    parser.add_argument("--product", default="an-quang-van-sao-zh")
    parser.add_argument("--version", default="auto", help="auto hoặc số nguyên dương như 1, 2, 3.")
    args = parser.parse_args()
    bundle = args.bundle or make_export(args.output, args.pages, args.include_images)
    validate_bundle(bundle)
    print("Gói kết quả:", bundle, flush=True)
    if args.github_repo:
        from github_release import publish_bundle
        publish_bundle(bundle, args.github_repo, args.product, args.version)


if __name__ == "__main__":
    main()
