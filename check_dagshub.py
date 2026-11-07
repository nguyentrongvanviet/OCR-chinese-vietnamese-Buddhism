"""Authenticate without displaying credentials, then check the selected bucket."""
import argparse
import re
import sys


def check_access(repo):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Repo phải ở dạng owner/repo.")
    import dagshub.auth
    from dagshub import get_repo_bucket_client
    dagshub.auth.get_token()  # OAuth URL may be displayed; never print the returned token.
    client = get_repo_bucket_client(repo)
    client.list_objects_v2(Bucket=repo.split("/", 1)[1], MaxKeys=1)
    print(f"DagsHub: xác thực và đọc bucket {repo} thành công.", flush=True)
    print("Quyền ghi sẽ được kiểm tra khi upload gói dữ liệu.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        check_access(args.repo)
    except Exception as error:
        # Do not echo SDK exceptions: request details can contain authentication data.
        print(f"Xác thực/truy cập DagsHub chưa thành công ({type(error).__name__}).", file=sys.stderr)
        print("Nếu OAuth lỗi hoặc hết hạn, chạy lại ô xác thực và dùng liên kết mới. "
              "Có thể chọn colab_secrets và tự thêm DAGSHUB_USER_TOKEN. "
              "Đặt UPLOAD_TO_DAGSHUB=False để tiếp tục OCR và lưu ZIP trên Drive.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
