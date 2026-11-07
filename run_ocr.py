"""Copy the source PDF to local runtime storage, then OCR into persistent storage."""

import argparse
from pathlib import Path
import shutil
import tempfile
import unicodedata

import zh_ocr_worker


def find_pdf(root):
    candidates = [path for path in root.rglob("*.pdf")
                  if unicodedata.normalize("NFC", path.name).endswith("Zh - 4.pdf")]
    if len(candidates) != 1:
        raise ValueError(f"Có {len(candidates)} bản Zh - 4.pdf; dùng --pdf để chỉ rõ đường dẫn.")
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-dir", type=Path, help="Ví dụ /content/drive/MyDrive/NLP_midterm_zh")
    parser.add_argument("--pdf", type=Path, help="Chỉ rõ PDF nếu không dùng chế độ tìm trong Drive.")
    parser.add_argument("--output", type=Path, help="Thư mục kết quả; có thể là Drive hoặc Kaggle working.")
    parser.add_argument("--output-name", default="ocr_zh_v01")
    parser.add_argument("--pages", default="3,4,5", help="3,4,5; 1-25; hoặc all")
    parser.add_argument("--work-dir", type=Path, default=Path(tempfile.gettempdir()) / "han-ocr-inputs")
    parser.add_argument("--pipeline-version", default="v1.6", choices=("v1.6", "v1.5", "v1"))
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--dagshub-repo", help="Tự xuất và upload kết quả sau lượt OCR, dạng owner/repo.")
    args = parser.parse_args()
    if not 72 <= args.dpi <= 600:
        parser.error("DPI phải trong khoảng 72–600.")
    if not args.output_name or Path(args.output_name).name != args.output_name or args.output_name in (".", ".."):
        parser.error("--output-name chỉ được là tên thư mục.")
    try:
        root = args.drive_dir.expanduser().resolve() if args.drive_dir else None
        if root is not None and not root.is_dir():
            raise FileNotFoundError(f"Chưa có {root}; mount Drive và upload PDF trước.")
        if args.pdf:
            pdf = args.pdf.expanduser().resolve()
        elif root is not None:
            pdf = find_pdf(root)
        else:
            parser.error("Dùng --drive-dir hoặc --pdf cùng --output.")
        if not pdf.is_file():
            raise FileNotFoundError(pdf)
        if args.output:
            output = args.output.expanduser().resolve()
        elif root is not None:
            output = root / args.output_name
        else:
            parser.error("Cần --output khi không dùng --drive-dir.")
        args.work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=args.work_dir) as local:
            local_pdf = Path(local) / "input.pdf"
            shutil.copy2(pdf, local_pdf)
            print("PDF nguồn:", pdf, flush=True)
            print("Kết quả:", output, flush=True)
            worker_args = argparse.Namespace(pdf=str(local_pdf), output=str(output),
                                             pages=args.pages, pipeline_version=args.pipeline_version,
                                             dpi=args.dpi)
            result = zh_ocr_worker.run(worker_args)
            if args.dagshub_repo:
                from export_results import make_export, upload_export
                bundle = make_export(output, args.pages)
                upload_export(bundle, args.dagshub_repo)
            return result
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
