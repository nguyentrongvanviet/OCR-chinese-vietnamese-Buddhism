# Hán OCR trên Google Colab

Repo quản lý code. Colab cung cấp GPU. Google Drive giữ PDF, kết quả và checkpoint.
Chỉ nhận dạng bản tiếng Trung; chưa dịch, dóng hàng hoặc tạo XLSX.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism/blob/main/OCR_Han_Colab.ipynb)

## Chạy

1. Đưa PDF tiếng Trung vào `My Drive/NLP_midterm_zh/source/`.
2. Bấm **Open in Colab**, chọn **Runtime > Change runtime type > GPU**.
3. Chạy ô clone, mount Drive, cài môi trường và chạy OCR.
4. Mặc định thử trang PDF `3,4,5`. Xem ảnh và text trước khi đổi `PAGES` thành `all`.
5. Khi runtime mới, chạy lại từ đầu với cùng đường dẫn đầu ra; trang có checkpoint hợp lệ được bỏ qua.

Notebook chỉ là launcher, không nhúng code OCR. Khi cập nhật file `.py` trên GitHub,
chạy lại ô clone/fetch để lấy phiên bản mới. Notebook đang mở không tự đồng bộ các ô `.ipynb`
từ GitHub; giữ các ô launcher ổn định và cập nhật logic trong script.

Có thể gọi trực tiếp từ một notebook trống:

```python
from google.colab import drive
drive.mount('/content/drive')
```

```bash
!git clone https://github.com/nguyentrongvanviet/OCR-chinese-vietnamese-Buddhism.git /content/han-ocr-colab
!python /content/han-ocr-colab/setup_colab.py
!/content/han-ocr-env/bin/python -u /content/han-ocr-colab/run_ocr.py --drive-dir /content/drive/MyDrive/NLP_midterm_zh --pages 3,4,5
```

Đổi `--pages 3,4,5` thành `--pages all` để chạy toàn bộ, hoặc `--pages 6-30` để chia khoảng.
Clone một lần trong mỗi runtime. Nếu đã clone, dùng ô launcher để fetch thay vì clone chồng lên thư mục cũ.

Đường dẫn tường minh, dùng được cả khi không tìm file từ Drive:

```bash
/content/han-ocr-env/bin/python run_ocr.py \
  --pdf "/content/drive/MyDrive/NLP_midterm_zh/source/book-Zh.pdf" \
  --output "/content/drive/MyDrive/NLP_midterm_zh/ocr_zh_v01" \
  --pages 3,4,5
```

## File trong repo

| File | Vai trò |
|---|---|
| `OCR_Han_Colab.ipynb` | Clone/fetch, mount Drive, cấu hình và gọi script. |
| `setup_colab.py` | Kiểm tra GPU, tạo Python 3.12 riêng và cài thư viện. |
| `run_ocr.py` | Tìm/copy PDF sang ổ runtime và khởi chạy worker. |
| `zh_ocr_worker.py` | OCR theo trang, lưu dữ liệu thô, kiểm tra checkpoint và ghép TXT. |
| `requirements-colab.txt` | Cố định các thư viện chính. |
| `test_workflow.py` | Kiểm tra lưu, tiếp tục, lỗi trang và checksum trên CPU. |
| `build_notebook.py` | Tạo lại launcher nếu cần, không nhúng worker. |

Môi trường: Python 3.12, PaddleOCR 3.7.0, PaddlePaddle GPU 3.2.1 CUDA 12.6,
pipeline PaddleOCR-VL v1.6. Suy luận trực tiếp trên GPU, không dựng vLLM server.
Colab L4/A100 phù hợp để thử nếu được cấp; T4 có thể thử bằng đường suy luận trực tiếp.
`setup_colab.py` kiểm tra tính toán GPU trước khi tải mô hình. Mô hình được tải ở lần OCR đầu.

## Đầu ra

Trong `My Drive/NLP_midterm_zh/ocr_zh_v01/`:

```text
config.json
environment-lock.txt
summary.json
NOTE.txt
han_ocr_partial.txt
han_ocr_full.txt                 # chỉ có khi mọi trang đã xử lý
runs/                           # commit, cấu hình lượt chạy và trạng thái
pages/
  page_0003/
    source.png
    raw.json
    text.txt
    status.json
```

- `raw.json`: giữ vùng chữ, nhãn và thứ tự đọc do pipeline dự đoán.
- `text.txt`: nối nội dung block theo thứ tự pipeline, không tự đổi giản thể/phồn thể.
- `partial`: có mã trang cho cả tài liệu, đánh dấu rõ trang chưa có kết quả.
- `full`: mọi trang đã xử lý, vẫn là OCR thô; không đồng nghĩa mọi chữ đã đúng.
- Trang OCR rỗng được giữ và ghi vào NOTE để xem ảnh gốc, không mặc định là trang trắng.

Checkpoint gồm checksum PDF, worker, các phiên bản chính và file đầu ra. Trang lỗi hoặc
file bị hỏng sẽ được xử lý lại. Khi đổi worker/mô hình/thư viện, dùng `--output-name ocr_zh_v02`
hoặc `--output` mới để tránh trộn dữ liệu khác cấu hình. Không cho hai phiên ghi cùng thư mục.

Mỗi lượt ghi commit vào `runs/`. `REF=main` trong launcher lấy code mới tại thời điểm fetch;
điền một tag hoặc commit cụ thể để tái lập. Không cập nhật repo giữa một lượt OCR.

## Điều GitHub giải quyết và không giải quyết

Code ở một chỗ, có lịch sử thay đổi, dễ sửa trên máy rồi push, giảm thao tác sao chép các ô notebook.
Notebook không còn là bản sao thứ hai của implementation.

Git clone không giữ môi trường, GPU hay tiến trình của Colab. Runtime mới vẫn có thể phải cài lại
thư viện và tải model. Dữ liệu trong `/content` có thể mất khi runtime bị xóa; checkpoint phải ở Drive.
Drive có độ trễ I/O nên PDF được copy sang ổ runtime trước khi đọc.

Không commit PDF, dữ liệu OCR, model weights, môi trường Python hoặc thông tin đăng nhập.
`.gitignore` bảo vệ các loại này khỏi thao tác add thông thường. Repo công khai chỉ chứa code và hướng dẫn.

## Giới hạn nhận dạng

Chưa chạy mô hình thật trên Colab GPU trong lần chuẩn bị repo. Các kiểm tra cục bộ dùng OCR giả lập
để kiểm tra checkpoint, không đo CER hay xác nhận khả năng nhận dạng chữ dọc.

Chưa tích hợp khử lem theo cặp. Trước hết thử ảnh gốc; nếu OCR lấy nhầm chữ xuyên mặt sau,
bỏ vùng chữ hoặc đảo cột, giữ kết quả pilot và bổ sung xử lý ảnh trên các cặp đã xác minh.
Không coi việc notebook chạy hết là bằng chứng text đúng. Không tự sửa chữ dị thể theo phỏng đoán.

## Kiểm tra trên CPU

```bash
python -m pip install -r requirements-test.txt
python -m unittest -v test_workflow
```

Các bài kiểm tra không tải mô hình OCR. Kiểm tra thực trên GPU cần chạy pilot và đối chiếu ảnh.

## Nguồn

- [PaddleOCR-VL: cài đặt, GPU, Python API](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [Colab FAQ: runtime, Drive và giới hạn tài nguyên](https://research.google.com/colaboratory/faq.html)
