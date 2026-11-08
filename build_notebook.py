"""Generate a thin Colab launcher; OCR/export implementations stay in Git."""
import argparse
import json
from pathlib import Path
import textwrap


def build(repo_url):
    cells = []
    def add(kind, source):
        cell = {"cell_type": kind, "id": f"han{len(cells):03d}", "metadata": {},
                "source": (textwrap.dedent(source).strip() + "\n").splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)

    add("markdown", """
    **GitHub chứa code + PDF gốc · Colab chạy GPU · Drive giữ checkpoint · GitHub Releases nhận TXT**

    Chọn Runtime > Change runtime type > GPU rồi chạy từ trên xuống.
    Không cần tự upload PDF. Mặc định thử trang 3–8; kiểm tra chữ và thứ tự cột trước khi đổi `PAGES` thành `all`.
    Repo hiện công khai: TXT đính kèm Release sẽ công khai.
    """)
    add("code", f"""
    from pathlib import Path
    import subprocess
    import sys

    def run_visible(command):
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1) as process:
            try:
                for line in process.stdout:
                    print(line, end="", flush=True)
                code = process.wait()
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
        if code:
            raise RuntimeError(f"Lệnh kết thúc với mã {{code}}; xem log phía trên.")

    REPO_URL = {repo_url!r} #@param {{type:"string"}}
    REF = "main" #@param {{type:"string"}}
    REPO_DIR = Path("/content/han-ocr-colab")
    if not REPO_DIR.exists():
        run_visible(["git", "clone", "--", REPO_URL, str(REPO_DIR)])
    else:
        remote = subprocess.check_output(["git", "-C", str(REPO_DIR), "remote", "get-url", "origin"], text=True).strip()
        if remote.removesuffix(".git") != REPO_URL.removesuffix(".git"):
            raise ValueError("Thư mục clone thuộc repo khác.")
        if subprocess.check_output(["git", "-C", str(REPO_DIR), "status", "--porcelain"], text=True).strip():
            raise RuntimeError("Bản clone có thay đổi cục bộ; lưu thay đổi trước khi cập nhật.")
    run_visible(["git", "-C", str(REPO_DIR), "fetch", "origin", REF])
    run_visible(["git", "-C", str(REPO_DIR), "checkout", "--detach", "FETCH_HEAD"])
    print("Code commit:", subprocess.check_output(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"], text=True).strip())
    """)
    add("code", """
    from google.colab import drive
    import hashlib
    import json
    drive.mount("/content/drive")

    DRIVE_DIR = "/content/drive/MyDrive/NLP_midterm_zh" #@param {type:"string"}
    OUTPUT_NAME = "ocr_zh_v02" #@param {type:"string"}
    PAGES = "3-8" #@param {type:"string"}
    GITHUB_REPO = "nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism" #@param {type:"string"}
    PRODUCT_NAME = "an-quang-van-sao-zh" #@param {type:"string"}
    RELEASE_VERSION = "auto" #@param {type:"string"}
    UPLOAD_TO_GITHUB = False #@param {type:"boolean"}
    source = json.loads((REPO_DIR / "assets/source_manifest.json").read_text())
    PDF_PATH = REPO_DIR / source["path"]
    assert PDF_PATH.stat().st_size == source["bytes"]
    assert hashlib.sha256(PDF_PATH.read_bytes()).hexdigest() == source["sha256"], "PDF sai checksum"
    OUTPUT_DIR = Path(DRIVE_DIR) / OUTPUT_NAME
    print("PDF đã có trong bản clone:", PDF_PATH, source["pdf_pages"], "trang")
    print("Checkpoint:", OUTPUT_DIR)
    """)
    add("code", """
    run_visible([sys.executable, "-u", str(REPO_DIR / "setup_colab.py")])
    ENV_PY = "/content/han-ocr-env/bin/python"
    """)
    add("markdown", """
    **Xuất TXT lên GitHub Releases**

    Tự thêm secret `GITHUB_TOKEN` trong thanh bên Secrets (biểu tượng chìa khóa), bật Notebook access.
    Token chỉ cần truy cập repo đích với quyền **Contents: Read and write**. Không paste token vào code/output.
    Mặc định `UPLOAD_TO_GITHUB=False`: mọi người có thể chạy OCR/lưu Drive mà không cần token.
    Chỉ bật `UPLOAD_TO_GITHUB=True` khi cần phát hành; điền repo của bạn hoặc repo mà bạn có quyền ghi.

    Tên TXT: `<owner>_<sản-phẩm>_v0001_HHMMSS_YYYY-MM-DD.txt`, giờ Việt Nam.
    `RELEASE_VERSION="auto"` tự lấy số kế tiếp trên GitHub, có tính các bản nháp đang upload.
    Chạy lại ô Upload với cùng gói sẽ tiếp tục cùng version; tạo gói xuất mới để phát hành version mới.
    """)
    add("code", """
    import os
    if UPLOAD_TO_GITHUB:
        from google.colab import userdata
        try:
            os.environ["GITHUB_TOKEN"] = userdata.get("GITHUB_TOKEN")
        except (userdata.SecretNotFoundError, userdata.NotebookAccessError, userdata.TimeoutException):
            raise RuntimeError("Thêm GITHUB_TOKEN vào Colab Secrets, bật Notebook access rồi chạy lại ô này.") from None
        run_visible([ENV_PY, "-u", str(REPO_DIR / "github_release.py"),
                     "--check-auth", "--repo", GITHUB_REPO])
    else:
        print("Chỉ lưu checkpoint và ZIP trên Drive.")
    """)
    add("code", """
    command = [ENV_PY, "-u", str(REPO_DIR / "run_ocr.py"),
               "--pdf", str(PDF_PATH), "--output", str(OUTPUT_DIR), "--pages", PAGES]
    if UPLOAD_TO_GITHUB:
        command.extend(["--github-repo", GITHUB_REPO, "--product", PRODUCT_NAME, "--version", RELEASE_VERSION])
    run_visible(command)
    """)
    add("code", """
    from IPython.display import display
    from PIL import Image
    summary = json.loads((OUTPUT_DIR / "summary.json").read_text())
    print("Đã xử lý:", len(summary["done_pages"]), "/", summary["total_pdf_pages"])
    print("Trang cần kiểm tra vì OCR rỗng:", summary["empty_pages_need_review"])
    PREVIEW_PAGE = 3 #@param {type:"integer"}
    page = OUTPUT_DIR / "pages" / f"page_{PREVIEW_PAGE:04d}"
    if (page / "source.png").exists():
        with Image.open(page / "source.png") as image:
            image.thumbnail((600, 1000))
            display(image.copy())
    if (page / "text.txt").exists():
        print((page / "text.txt").read_text(encoding="utf-8"))
    latest = OUTPUT_DIR / "latest_export.json"
    if latest.exists():
        bundle = Path(json.loads(latest.read_text())["path"])
        print("ZIP trên Drive:", bundle / "bundle.zip")
        receipt = bundle / "github_release" / "receipt.json"
        print(receipt.read_text() if receipt.exists() else "Upload chưa hoàn tất; chạy ô thử lại bên dưới.")
    """)
    add("markdown", """
    **Upload lại khi mạng lỗi — không OCR lại**

    Chạy ô dưới nếu upload thất bại. Gói giữ nguyên mã lần xuất, kiểm tra SHA-256 từng file sau khi tải lên,
    và chỉ công khai Release khi TXT, manifest và checksum đã được tải đọc lại để kiểm tra SHA-256.
    `han.txt` chứa toàn bộ trang thuộc phạm vi chạy; `pages.jsonl` giữ số trang và JSON OCR gốc trên Drive.
    File trên Release có tên theo tài khoản, sản phẩm, version, giờ và ngày; không ghi đè bản đã phát hành.
    """)
    add("code", """
    if UPLOAD_TO_GITHUB:
        latest = json.loads((OUTPUT_DIR / "latest_export.json").read_text())
        run_visible([ENV_PY, "-u", str(REPO_DIR / "export_results.py"),
                     "--bundle", latest["path"], "--github-repo", GITHUB_REPO,
                     "--product", PRODUCT_NAME, "--version", RELEASE_VERSION])
    else:
        print("Upload đang tắt. ZIP đã được lưu trên Drive.")
    """)
    add("markdown", """
    **Chạy toàn bộ**

    Đổi `PAGES` thành `all`, chạy lại ô cấu hình và ô OCR. Các checkpoint hợp lệ được bỏ qua.
    `han_ocr_full.txt` trên Drive chỉ xuất hiện khi đủ mọi trang; manifest trên Release có `complete_book=true` khi đủ toàn bộ.
    Dữ liệu vẫn là OCR thô, chưa khử lem theo cặp, chưa hiệu đính hoặc gióng hàng.
    Mỗi gói xuất có thư mục riêng trên Drive: `exports/<mã lần xuất>/`.
    Thành viên trong nhóm tải TXT từ cùng tag GitHub Release để có cùng dữ liệu. Tránh chạy đồng thời vào cùng thư mục Drive.
    Không cập nhật code giữa một lượt OCR. Để tái lập, dùng commit cụ thể ở `REF`;
    đổi `OUTPUT_NAME` khi thay model/worker làm thay đổi cấu hình.
    """)
    return {"nbformat":4,"nbformat_minor":5,"metadata":{
        "accelerator":"GPU","colab":{"name":"OCR_Han_Colab.ipynb","provenance":[]},
        "kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
        "language_info":{"name":"python"}},"cells":cells}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url",default="https://github.com/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism.git")
    args=parser.parse_args()
    path=Path(__file__).resolve().parent / "OCR_Han_Colab.ipynb"
    path.write_text(json.dumps(build(args.repo_url),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(path)
