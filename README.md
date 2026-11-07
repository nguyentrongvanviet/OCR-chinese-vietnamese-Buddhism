# OCR chữ Hán trên Colab, chia sẻ kết quả qua DagsHub

[Chạy notebook trên Colab](https://colab.research.google.com/github/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism/blob/main/OCR_Han_Colab.ipynb)

GitHub chứa code và **một bản PDF nguồn cố định** (`assets/pdf/an_quang_van_sao_zh_4.pdf`, 214 trang, 51.832.050 byte). Khi Colab clone repo, PDF có sẵn; không cần upload thủ công. `assets/source_manifest.json` ghi SHA-256 và notebook kiểm tra trước khi chạy. Tránh sửa/commit lại PDF nhiều lần vì làm lịch sử Git phình to. Với nhiều sách hoặc bản scan lớn hơn, chuyển nguồn sang kho dữ liệu và tải theo manifest.

Colab chạy GPU; Drive giữ checkpoint qua những lần ngắt runtime; DagsHub Storage nhận các gói kết quả có mã riêng để cả nhóm dùng chung. Repo DagsHub đang cấu hình là **công khai**: https://dagshub.com/nguyentrongvanviet/OCR_chinese_to_vietnamese_for_NLP . Chỉ gói dữ liệu OCR được gửi lên; không gửi token hay PDF nguồn trong bước export.

## Chạy

1. Mở Colab, chọn **Runtime → Change runtime type → GPU**.
2. Chạy từ trên xuống. Ô clone lấy code + PDF. Drive được mount để lưu checkpoint.
3. Cài môi trường Python 3.12 riêng, Paddle GPU 3.2.1/CUDA 12.6, PaddleOCR 3.7.0 với PaddleOCR-VL v1.6. Log hiển thị trực tiếp. Lần đầu tải các thư viện/model có thể lâu. SentencePiece được ghim 0.2.1 để tránh lỗi Protobuf của bản mới; setup kiểm tra import tokenizer trước OCR.
4. Mặc định `AUTH_METHOD="oauth"`: ô xác thực hiển thị liên kết OAuth; mở và tự xác nhận nếu cần. Nếu OAuth lỗi/hết hạn, chạy lại ô xác thực và dùng liên kết mới. Để chạy thường xuyên, chọn `AUTH_METHOD="colab_secrets"`, tự thêm secret `DAGSHUB_USER_TOKEN` trong thanh bên Secrets và bật Notebook access. Mỗi thành viên dùng token riêng đã được cấp quyền ghi repo. Token chỉ truyền qua môi trường runtime, không nằm trong code hoặc ZIP. SDK cache OAuth cũng nằm trong `/content`, không nằm trên Drive.

   Nếu chưa cần upload, đặt `UPLOAD_TO_DAGSHUB=False`: vẫn chạy OCR, ghép TXT và tạo ZIP trên Drive; bỏ qua OAuth. Bật lại upload và chạy ô xác thực rồi ô Upload lại khi đã sẵn sàng.
5. Mặc định `PAGES="3,4,5"`. Ô OCR tạo checkpoint rồi tự đóng gói và upload lên DagsHub. Đối chiếu ảnh với chữ trước khi chạy nhiều trang.
6. Đổi `PAGES="all"`, chạy lại ô cấu hình và ô OCR để xử lý toàn bộ. Trang có checkpoint hợp lệ được bỏ qua.

`REF="main"` lấy phiên bản hiện tại tại lúc chạy ô clone. Điền commit cụ thể để tái lập. Không cập nhật code giữa lượt OCR. Nếu nguồn, worker hay phiên bản model đổi, dùng `OUTPUT_NAME` mới theo thông báo. Không cho nhiều người ghi đồng thời cùng thư mục Drive; mỗi lượt chạy/nhánh thử nghiệm dùng tên riêng.

## Nhận sản phẩm

Mỗi lượt chạy tạo thư mục trên Drive:

```
NLP_midterm_zh/ocr_zh_v01/
  config.json                 # SHA nguồn, worker và cấu hình
  environment-lock.txt        # phiên bản thực tế đã cài
  runs/                       # lịch sử các lần chạy và commit
  pages/page_0003/
    source.png                # ảnh gốc đầy đủ, hoặc render nếu cần
    raw.json                  # JSON nguyên bản từ OCR
    text.txt                  # UTF-8 cho riêng trang
    status.json               # checksum, thời gian, trạng thái
  han_ocr_partial.txt         # đủ dấu trang PDF, trang chưa chạy được ghi rõ
  han_ocr_full.txt            # chỉ xuất hiện khi xử lý đủ 214 trang
  summary.json
  exports/<export_id>/
    han.txt                   # ghép các trang trong phạm vi lượt xuất
    pages.jsonl               # số trang + text + JSON OCR gốc
    manifest.json             # trang đủ/thiếu/rỗng, nguồn và cấu hình
    pages/                    # raw.json, text.txt, status.json từng trang
    environment-lock.txt
    NOTE.txt
    checksums.sha256
    bundle.zip                # tải một file cho cả nhóm
    upload_receipt.json       # đường dẫn DagsHub khi truyền thành công
  latest_export.json
```

DagsHub Storage lưu tại `exports/<12 ký tự SHA PDF>/<export_id>/`, kèm `_SUCCESS.json` **sau khi** upload và tải đọc lại để xác minh SHA-256 mọi file. Mỗi mã lần xuất là một snapshot riêng, không ghi đè sản phẩm của người khác. `complete_scope=true` nghĩa là đủ phạm vi đã chọn; `complete_book=true` mới nghĩa là đủ cả sách. `_SUCCESS` chỉ xác nhận truyền file, không xác nhận OCR đúng.

Cả nhóm chọn cùng một `export_id`, tải `bundle.zip` trong tab **Data / DagsHub Storage** của repo, giải nén và đọc `han.txt` hoặc `pages.jsonl`. Dùng manifest để biết gói gồm trang nào. Bucket là kho S3 tương thích; snapshot được tổ chức bởi code này, chưa phải lịch sử DVC hoặc bản dữ liệu đã duyệt.

## Khi Colab/mạng ngắt

- OCR bị ngắt: chạy lại cùng cấu hình. Checkpoint bị thiếu hoặc sai checksum được chạy lại; trang hoàn thành được bỏ qua. Không cần OCR lại toàn bộ.
- Upload thất bại: checkpoint và ZIP vẫn nằm trên Drive. Chạy ô **Upload lại**; nó dùng gói lần xuất gần nhất, bỏ qua file đã truyền đúng và không chạy OCR.
- Runtime mới: chạy lại các ô đầu để clone, mount, cài thư viện, xác thực rồi tiếp tục.
- Không upload được vẫn lấy ZIP trực tiếp trên Drive. Để chỉ đóng gói mà không cần DagsHub, chạy lệnh bên dưới.

```bash
python export_results.py --output /path/to/ocr_zh_v01 --pages all
python export_results.py --bundle /path/to/ocr_zh_v01/exports/EXPORT_ID \
  --dagshub-repo nguyentrongvanviet/OCR_chinese_to_vietnamese_for_NLP
```

CLI OCR cũng hỗ trợ Kaggle hoặc máy GPU:

```bash
python run_ocr.py --pdf assets/pdf/an_quang_van_sao_zh_4.pdf \
  --output /path/to/results --pages 3,4,5 \
  --dagshub-repo nguyentrongvanviet/OCR_chinese_to_vietnamese_for_NLP
```

Cài `requirements-export.txt` để dùng DagsHub. `--include-images` của exporter bổ sung ảnh trang vào gói khi cần đối chiếu; mặc định chỉ xuất chữ và JSON để truyền nhẹ hơn.

## Giới hạn OCR

Đây là **OCR thô**, chưa khử chữ xuyên mặt sau theo cặp, chưa hiệu đính, chưa chuyển phồn thể sang giản thể, chưa dịch và chưa gióng hàng với tiếng Việt. Ảnh gốc giữ lại để đối chiếu. Văn bản giữ các block theo thứ tự mô hình, không tự sửa chữ. Chữ lem, triện và cột dọc có thể bị đọc nhầm, đọc thêm hoặc đảo thứ tự. Trang không rỗng vẫn có thể sai. `quality_reviewed=false` được giữ trong manifest để không nhầm với dữ liệu đã duyệt.

## Kiểm tra code không cần GPU

```bash
python -m pip install -r requirements-test.txt
python -m unittest -v test_workflow test_exports test_launcher
python build_notebook.py
```

Các test kiểm tra phục hồi sau ngắt, phát hiện checkpoint hỏng, không trộn cấu hình, giữ dấu trang thiếu/rỗng, xuất UTF-8, CLI tạo ZIP khi không upload, notebook khớp generator và upload có checksum/thử lại. Chúng không đo chất lượng nhận dạng chữ Hán.

MIT trong repo áp dụng cho code. PDF giữ thông tin nguồn gốc riêng trong manifest; repo không tuyên bố cấp lại giấy phép cho nội dung sách.

Xác thực dùng cơ chế chính thức của [DagsHub SDK](https://dagshub.com/docs/client/reference/auth); bucket dùng [DagsHub Storage](https://dagshub.com/docs/feature_guide/dagshub_storage/).
