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
    **GitHub chứa code + PDF gốc · Colab chạy GPU · Drive giữ checkpoint · DagsHub nhận sản phẩm**

    Chọn Runtime > Change runtime type > GPU rồi chạy từ trên xuống.
    Không cần tự upload PDF. Mặc định thử trang 3–5; kiểm tra chữ và thứ tự cột trước khi đổi `PAGES` thành `all`.
    DagsHub hiện là repo công khai: các kết quả được upload sẽ công khai.
    """)
    add("code", f"""
    from pathlib import Path
    import subprocess
    import sys

    def run_visible(command):
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
            code = process.wait()
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
    OUTPUT_NAME = "ocr_zh_v01" #@param {type:"string"}
    PAGES = "3,4,5" #@param {type:"string"}
    DAGSHUB_REPO = "nguyentrongvanviet/OCR_chinese_to_vietnamese_for_NLP" #@param {type:"string"}
    source = json.loads((REPO_DIR / "assets/source_manifest.json").read_text())
    PDF_PATH = REPO_DIR / source["path"]
    assert PDF_PATH.stat().st_size == source["bytes"]
    assert hashlib.sha256(PDF_PATH.read_bytes()).hexdigest() == source["sha256"], "PDF sai checksum"
    OUTPUT_DIR = Path(DRIVE_DIR) / OUTPUT_NAME
    print("PDF đã có trong bản clone:", PDF_PATH, source["pdf_pages"], "trang")
    print("Checkpoint:", OUTPUT_DIR)
    """)
    add("code", """
    run_visible([sys.executable, "-u", str(REPO_DIR / "setup_colab.py"), "--with-export"])
    ENV_PY = "/content/han-ocr-env/bin/python"
    """)
    add("markdown", """
    **Xác thực DagsHub một lần trong runtime**

    Ô sau hiển thị liên kết đăng nhập OAuth nếu chưa xác thực. Mở liên kết và tự xác nhận.
    Không đưa token vào code, Git, Drive hoặc output notebook. SDK giữ thông tin xác thực trong runtime tạm thời.
    """)
    add("code", """
    auth_code = (
        "import dagshub.auth; from dagshub import get_repo_bucket_client; "
        "dagshub.auth.get_token(); "
        f"client=get_repo_bucket_client({DAGSHUB_REPO!r}); "
        f"client.list_objects_v2(Bucket={DAGSHUB_REPO.split('/')[-1]!r}, MaxKeys=1); "
        "print('DagsHub: xác thực và truy cập bucket thành công.')"
    )
    run_visible([ENV_PY, "-u", "-c", auth_code])
    """)
    add("code", """
    run_visible([
        ENV_PY, "-u", str(REPO_DIR / "run_ocr.py"),
        "--pdf", str(PDF_PATH), "--output", str(OUTPUT_DIR), "--pages", PAGES,
        "--dagshub-repo", DAGSHUB_REPO,
    ])
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
        receipt = bundle / "upload_receipt.json"
        print(receipt.read_text() if receipt.exists() else "Upload chưa hoàn tất; chạy ô thử lại bên dưới.")
    """)
    add("markdown", """
    **Upload lại khi mạng lỗi — không OCR lại**

    Chạy ô dưới nếu upload thất bại. Gói giữ nguyên mã lần xuất, kiểm tra SHA-256 từng file sau khi tải lên,
    và chỉ ghi `_SUCCESS.json` khi truyền đủ dữ liệu. `_SUCCESS` xác nhận truyền file, không xác nhận OCR chính xác.
    `han.txt` chứa toàn bộ trang thuộc phạm vi chạy; `pages.jsonl` giữ số trang và JSON OCR gốc.
    """)
    add("code", """
    latest = json.loads((OUTPUT_DIR / "latest_export.json").read_text())
    run_visible([ENV_PY, "-u", str(REPO_DIR / "export_results.py"),
                 "--bundle", latest["path"], "--dagshub-repo", DAGSHUB_REPO])
    """)
    add("markdown", """
    **Chạy toàn bộ**

    Đổi `PAGES` thành `all`, chạy lại ô cấu hình và ô OCR. Các checkpoint hợp lệ được bỏ qua.
    `han_ocr_full.txt` trên Drive chỉ xuất hiện khi đủ mọi trang; gói DagsHub có `complete_book=true` khi đủ toàn bộ.
    Dữ liệu vẫn là OCR thô, chưa khử lem theo cặp, chưa hiệu đính hoặc gióng hàng.
    Mỗi gói xuất có thư mục riêng: `exports/<mã PDF>/<mã lần xuất>/`.
    Thành viên trong nhóm dùng cùng gói ZIP để có cùng dữ liệu. Tránh chạy đồng thời vào cùng thư mục Drive.
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
