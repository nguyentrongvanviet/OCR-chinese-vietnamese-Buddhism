# OCR chữ Hán: Colab → Drive → GitHub Releases

[Mở notebook Colab](https://colab.research.google.com/github/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism/blob/main/OCR_Han_Colab.ipynb)

GitHub chứa code và PDF nguồn cố định; Colab chạy GPU; Drive giữ checkpoint; **GitHub Releases phát hành file TXT theo phiên bản** để cả nhóm tải cùng một bản.

## Chạy notebook

1. Chọn Runtime → Change runtime type → GPU, chạy từ trên xuống.
2. Ô clone lấy cả PDF `assets/pdf/an_quang_van_sao_zh_4.pdf` (214 trang). Notebook kiểm tra SHA-256 theo `assets/source_manifest.json`; không cần upload PDF thủ công.
3. Drive giữ kết quả trong `My Drive/NLP_midterm_zh/ocr_zh_v02/`. Mặc định thử `PAGES="3-8"`; đặt `PAGES="all"` để xử lý toàn bộ sau khi đối chiếu chất lượng.
4. Cài môi trường Python 3.12 riêng với Paddle GPU 3.2.1/cu126 và PaddleOCR 3.7.0, model VL v1.6. Lần đầu cài thư viện/tải model có thể lâu. SentencePiece 0.2.1 được ghim để tránh lỗi Protobuf.
5. Để xuất TXT lên GitHub, tự thêm **`GITHUB_TOKEN`** trong thanh bên **Secrets**, bật **Notebook access**. Token chỉ cần chọn repo đích và quyền **Contents: Read and write**. Không đưa token vào code hoặc output. Mỗi thành viên dùng token riêng; chỉ người có quyền ghi repo mới phát hành được.
6. Mặc định `UPLOAD_TO_GITHUB=False`: người khác có thể clone và chạy OCR/lưu Drive mà không cần thiết lập token. Khi cần phát hành, bật `UPLOAD_TO_GITHUB=True`, điền `GITHUB_REPO` của mình hoặc repo có quyền ghi, `PRODUCT_NAME` và `RELEASE_VERSION`. Ô OCR sẽ tạo gói trên Drive rồi phát hành TXT lên Releases.

## Quy tắc tên file

```
<tài_khoản>_<sản-phẩm>_v<mã-số>_<HHMMSS>_<YYYY-MM-DD>.txt
```

Ví dụ minh họa:

```
nguyentrongvanviet_an-quang-van-sao-zh_v0001_110500_2026-11-08.txt
```

- **Tài khoản:** owner của `GITHUB_REPO`, không phải email hoặc tên tài khoản Google.
- **Sản phẩm:** `PRODUCT_NAME`; chữ Việt được bỏ dấu, khoảng trắng thành dấu gạch ngang. Ví dụ `Ấn Quang Văn Sao Zh` → `an-quang-van-sao-zh`.
- **Version:** `RELEASE_VERSION="auto"` đọc các Release của cùng tài khoản/sản phẩm để chọn số kế tiếp; `v0001`, `v0002`, ... Số tiếp tục dài ra khi vượt 9999. Có thể nhập số nguyên dương chưa dùng.
- **Thời gian/ngày:** giờ Việt Nam, múi giờ `Asia/Ho_Chi_Minh` (UTC+7), ghi tại lúc tạo kế hoạch phát hành. Thử upload lại giữ nguyên timestamp/version.
- **Tag:** `ocr-<tài_khoản>-<sản-phẩm>-v0001`. Tên Release đầy đủ có cả giờ/ngày như tên TXT.

Mỗi bản phát hành có 3 assets cùng tiền tố:

```
...txt                 # văn bản ghép trong phạm vi trang đã chọn
...manifest.json       # phạm vi trang, nguồn, cấu hình, version và thời gian
...sha256              # SHA-256 của TXT và manifest
```

Code tạo **draft**, upload từng asset, tải đọc lại để kiểm tra SHA-256, sau đó mới công khai Release. Không ghi đè asset khác nội dung hoặc version của bản khác. Bản chưa đủ toàn bộ sách được đánh dấu **prerelease**; `complete_book` và `quality_reviewed` trong manifest cho biết phạm vi và chất lượng. `complete_book=true` chỉ xác nhận đủ trang đã xử lý, không xác nhận nhận dạng chữ đúng.

Chạy lại Upload với **cùng gói xuất** tiếp tục cùng version, không tạo thêm bản. Để tạo phiên bản mới, tạo gói xuất mới qua ô OCR (checkpoint hợp lệ sẽ được bỏ qua) hoặc `export_results.py --output ...`.

Repo hiện công khai nên TXT/metadata trong Releases cũng công khai. Thành viên tải từ **Releases → Assets**, chọn cùng tag để dùng cùng dữ liệu. File **Source code.zip** do GitHub tự tạo là code theo tag; TXT kết quả là asset riêng có tên như trên. Release không thay thế checkpoint trên Drive.

## Kết quả trên Drive

```
ocr_zh_v02/
  config.json
  environment-lock.txt
  runs/                       # lần chạy, commit, trang đã chọn
  pages/page_0003/
    source.png                # ảnh trang đầy đủ
    raw.json                  # JSON OCR gốc
    text.txt                  # UTF-8 từng trang
    status.json               # checksum, thời gian, trạng thái
  han_ocr_partial.txt         # dấu trang đầy đủ; trang chưa chạy có marker
  han_ocr_full.txt            # chỉ xuất hiện khi xử lý đủ mọi trang
  summary.json
  exports/<export_id>/
    han.txt
    pages.jsonl
    manifest.json
    NOTE.txt
    checksums.sha256
    bundle.zip                # toàn bộ chữ/JSON của phạm vi xuất
    github_release/
      plan.json               # giữ nguyên version/thời gian khi thử lại
      assets/                 # TXT được đặt tên theo quy tắc
      receipt.json            # link Release và link TXT đã xác minh
      upload_pending.json     # chỉ có khi phát hành chưa hoàn tất
  latest_export.json
```

Ảnh gốc, JSON OCR từng trang và checkpoint vẫn nằm trên Drive. Bước phát hành chỉ gửi TXT, manifest, checksum; không gửi PDF, credential, hoặc cả thư mục Drive.

## Khi Colab hoặc mạng bị ngắt

- OCR bị ngắt: chạy lại cùng cấu hình; checkpoint hợp lệ được bỏ qua. Trang thiếu hoặc hỏng checksum được xử lý lại.
- Upload thất bại: ZIP/TXT và kế hoạch vẫn ở Drive; chạy ô **Upload lại**. Không cần OCR lại. Đừng thay `PRODUCT_NAME`, repo hoặc version khi đang tiếp tục cùng gói.
- Token thiếu/hết quyền: sửa Colab Secrets, chạy lại ô xác thực rồi Upload lại.
- Một asset remote khác nội dung: code dừng để bảo vệ bản cũ. Tạo gói xuất mới cho version mới.
- Runtime mới: chạy lại clone, mount, cài thư viện, nạp secret rồi tiếp tục. Chọn `REF` là commit cụ thể để tái lập.
- Không cho nhiều lượt chạy ghi chung thư mục checkpoint Drive. Mỗi cấu hình/thử nghiệm dùng `OUTPUT_NAME` riêng.

## CLI

Exporter/publisher chỉ dùng thư viện chuẩn Python, không cần GPU để xuất TXT đã có. Cung cấp `GITHUB_TOKEN` qua môi trường chạy, không viết trực tiếp vào lệnh hoặc file được commit.

```bash
# Chỉ đóng gói checkpoint hiện có
python export_results.py --output /path/to/ocr_zh_v02 --pages 3-8

# Phát hành hoặc tiếp tục upload cùng một gói
python export_results.py --bundle /path/to/exports/EXPORT_ID \
  --github-repo nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism \
  --product an-quang-van-sao-zh --version auto

# Phát hành một TXT có sẵn, không cần OCR
python github_release.py --txt /path/to/han_6_pages.txt \
  --metadata /path/to/metadata.json \
  --repo nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism \
  --product an-quang-van-sao-zh --version auto

# OCR và tự xuất TXT lên GitHub
python run_ocr.py --pdf assets/pdf/an_quang_van_sao_zh_4.pdf \
  --output /path/to/results --pages 3-8 \
  --github-repo nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism \
  --product an-quang-van-sao-zh --version auto
```

Với TXT có sẵn, metadata nên có `scope_pages`, `source_pdf_sha256`, `complete_book`, `quality_reviewed`. Không có metadata thì bản phát hành không tuyên bố đủ cả sách. Mỗi TXT/metadata giữ một kế hoạch trong `.github_releases/` cạnh TXT; muốn phát hành lại nội dung đó thành version mới, chọn thư mục `--state-dir` mới. GitHub giới hạn mỗi asset nhỏ hơn 2 GiB.

## Giới hạn và kiểm tra

Đây là **OCR thô**, chưa khử lem theo hai mặt giấy, chưa hiệu đính, chưa dịch/chuyển phồn–giản và chưa gióng hàng với tiếng Việt. Mô hình có thể đọc thêm chữ xuyên mặt sau hoặc sai thứ tự cột dọc. Trang có text vẫn cần đối chiếu ảnh. Bản thử 6 trang là trang PDF 3–8, không gồm bìa.

Worker dùng `use_queues=False` và mặc định `FLAGS_allocator_strategy=naive_best_fit` trước khi import Paddle để tránh lỗi kẹt GPU đã được báo tại [PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693). Cấu hình được ghi trong `config.json`; chuyển từ worker cũ cần thư mục kết quả mới để tránh trộn checkpoint.

```bash
python -m pip install -r requirements-test.txt
python -m unittest -v test_workflow test_exports test_launcher test_releases
python build_notebook.py
```

Test kiểm tra checkpoint/phục hồi, UTF-8, gói xuất, notebook, tên version/giờ Việt Nam, upload bị ngắt, xung đột phiên bản, xác minh checksum và công khai sau khi truyền đủ assets. Test không đo độ chính xác OCR chữ Hán.

API sử dụng theo [GitHub Releases](https://docs.github.com/en/rest/releases/releases) và [Release Assets](https://docs.github.com/en/rest/releases/assets). MIT trong repo áp dụng cho code; repo không tuyên bố cấp lại giấy phép cho nội dung PDF.
