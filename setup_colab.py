"""Install an isolated Python 3.12 OCR environment in a Colab NVIDIA runtime."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-dir", type=Path, default=Path("/content/han-ocr-env"))
    args = parser.parse_args()
    if shutil.which("nvidia-smi") is None:
        parser.error("Chưa có NVIDIA GPU. Chọn Runtime > Change runtime type > GPU.")
    gpu = subprocess.run(["nvidia-smi"], check=True, text=True, capture_output=True)
    print(gpu.stdout, flush=True)
    cuda = re.search(r"CUDA Version:\s*([0-9.]+)", gpu.stdout)
    if cuda and tuple(map(int, cuda.group(1).split(".")[:2])) < (12, 6):
        parser.error("Cần driver hỗ trợ CUDA 12.6 trở lên. Chọn runtime GPU mới.")

    env_dir = args.env_dir.expanduser().resolve()
    python = env_dir / "bin" / "python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "pip", "install", "uv"], check=True)
        subprocess.run([sys.executable, "-m", "uv", "python", "install", "3.12"], check=True)
        subprocess.run([sys.executable, "-m", "uv", "venv", "--seed", "--python", "3.12",
                        str(env_dir)], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "paddlepaddle-gpu==3.2.1", "-i",
                    "https://www.paddlepaddle.org.cn/packages/stable/cu126/"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-r",
                    str(ROOT / "requirements-colab.txt")], check=True)
    subprocess.run([str(python), "-m", "pip", "check"], check=True)
    check = """
import paddle
from paddleocr import PaddleOCRVL
assert paddle.is_compiled_with_cuda(), 'Paddle đang dùng bản CPU.'
assert paddle.device.cuda.device_count() > 0, 'Paddle không thấy GPU.'
paddle.set_device('gpu:0')
assert paddle.ones([2, 2]).sum().item() == 4
print('GPU:', paddle.device.cuda.get_device_name(0))
print('Paddle:', paddle.__version__)
"""
    subprocess.run([str(python), "-u", "-c", check], check=True)
    print(f"Môi trường sẵn sàng: {python}", flush=True)


if __name__ == "__main__":
    main()
