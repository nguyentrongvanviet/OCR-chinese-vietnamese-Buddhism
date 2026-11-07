"""Generate the thin Colab launcher; implementation stays in repository scripts."""

import argparse
import json
from pathlib import Path
import textwrap


def build(repo_url):
    cells = []

    def add(kind, source):
        item = {"cell_type": kind, "id": f"han{len(cells):03d}", "metadata": {},
                "source": (textwrap.dedent(source).strip() + "\n").splitlines(keepends=True)}
        if kind == "code":
            item.update(execution_count=None, outputs=[])
        cells.append(item)

    add("markdown", """
    **OCR chữ Hán: GitHub giữ code, Colab chạy GPU, Drive giữ dữ liệu**

    Chọn Runtime > Change runtime type > GPU. Đưa PDF vào
    `My Drive/NLP_midterm_zh/source/`. Chạy các ô từ trên xuống.
    Mặc định thử trang 3–5; đổi `PAGES` thành `all` sau khi kiểm tra.
    Notebook không chứa bản sao code xử lý; mọi thay đổi nằm trong repo.
    """)
    add("code", f"""
    from pathlib import Path
    import subprocess
    import sys

    REPO_URL = {repo_url!r} #@param {{type:"string"}}
    REF = "main" #@param {{type:"string"}}
    REPO_DIR = Path("/content/han-ocr-colab")
    if "YOUR_USERNAME" in REPO_URL:
        raise ValueError("Điền URL GitHub của repo trước.")
    if not REPO_DIR.exists():
        subprocess.run(["git", "clone", "--", REPO_URL, str(REPO_DIR)], check=True)
    else:
        remote = subprocess.run(["git", "-C", str(REPO_DIR), "remote", "get-url", "origin"],
                                text=True, capture_output=True, check=True).stdout.strip()
        if remote.removesuffix(".git") != REPO_URL.removesuffix(".git"):
            raise ValueError("Thư mục clone hiện tại thuộc repo khác.")
        dirty = subprocess.run(["git", "-C", str(REPO_DIR), "status", "--porcelain"],
                               text=True, capture_output=True, check=True).stdout.strip()
        if dirty:
            raise RuntimeError("Bản clone có thay đổi cục bộ; lưu thay đổi trước khi cập nhật.")
    subprocess.run(["git", "-C", str(REPO_DIR), "fetch", "origin", REF], check=True)
    subprocess.run(["git", "-C", str(REPO_DIR), "checkout", "--detach", "FETCH_HEAD"], check=True)
    commit = subprocess.run(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"],
                            text=True, capture_output=True, check=True).stdout.strip()
    print("Code commit:", commit)
    """)
    add("code", """
    from google.colab import drive
    drive.mount("/content/drive")

    DRIVE_DIR = "/content/drive/MyDrive/NLP_midterm_zh" #@param {type:"string"}
    OUTPUT_NAME = "ocr_zh_v01" #@param {type:"string"}
    PAGES = "3,4,5" #@param {type:"string"}
    """)
    add("code", """
    subprocess.run([sys.executable, str(REPO_DIR / "setup_colab.py")], check=True)
    """)
    add("code", """
    subprocess.run([
        "/content/han-ocr-env/bin/python", "-u", str(REPO_DIR / "run_ocr.py"),
        "--drive-dir", DRIVE_DIR, "--output-name", OUTPUT_NAME, "--pages", PAGES,
    ], check=True)
    """)
    add("code", """
    import json
    from IPython.display import display
    from PIL import Image

    output = Path(DRIVE_DIR) / OUTPUT_NAME
    print((output / "NOTE.txt").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    print("Đã xử lý:", len(summary["done_pages"]), "/", summary["total_pdf_pages"])
    PREVIEW_PAGE = 3 #@param {type:"integer"}
    page = output / "pages" / f"page_{PREVIEW_PAGE:04d}"
    if (page / "source.png").exists():
        with Image.open(page / "source.png") as image:
            image.thumbnail((600, 1000))
            display(image.copy())
    if (page / "text.txt").exists():
        print((page / "text.txt").read_text(encoding="utf-8"))
    """)
    add("markdown", """
    **Tiếp tục chạy**

    Sau khi kiểm tra pilot, đổi `PAGES` thành `all` hoặc một khoảng như `6-30`, rồi chạy lại ô OCR.
    Khi runtime mới: chạy lại các ô từ đầu; checkpoint hợp lệ trên Drive được bỏ qua.
    Clone, cài thư viện và tải model vẫn có thể cần thực hiện lại trong runtime mới.

    `REF=main` lấy code mới tại thời điểm chạy ô clone. Có thể điền tag hoặc commit cụ thể để tái lập;
    không cập nhật code giữa một lượt OCR. Thay đổi worker/mô hình có thể yêu cầu `OUTPUT_NAME` mới.

    `han_ocr_full.txt` chỉ có khi mọi trang đã xử lý; văn bản vẫn là OCR thô.
    Chưa khử lem theo cặp hoặc xác nhận độ chính xác OCR. Xem README trong repo để biết giới hạn.
    """)
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"accelerator": "GPU", "colab": {"name": "OCR_Han_Colab.ipynb", "provenance": []},
                         "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}}, "cells": cells}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url", default="https://github.com/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism.git")
    args = parser.parse_args()
    path = Path(__file__).resolve().parent / "OCR_Han_Colab.ipynb"
    path.write_text(json.dumps(build(args.repo_url), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)
