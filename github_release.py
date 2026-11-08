"""Publish UTF-8 TXT snapshots to GitHub Releases using only the Python standard library."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
from zoneinfo import ZoneInfo

from zh_ocr_worker import sha256, write_json, write_text

TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class GitHubError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub API HTTP {status}. Kiểm tra mạng, token và quyền Contents: write của repo.")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("Từ chối chuyển hướng không dùng HTTPS.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


class GitHubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not self.token or not self.token.strip():
            raise ValueError("Thiếu GITHUB_TOKEN. Thêm token vào Colab Secrets và bật Notebook access.")
        self.opener = build_opener(SafeRedirect())

    def request(self, method, path, payload=None, file=None, binary=False):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        if urlsplit(url).hostname not in ("api.github.com", "uploads.github.com"):
            raise ValueError("Endpoint GitHub không hợp lệ.")
        headers = {"Authorization": f"Bearer {self.token}", "User-Agent": "han-ocr-release",
                   "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        stream = None
        try:
            if file is not None:
                stream = Path(file).open("rb")
                data = stream
                headers["Content-Length"] = str(Path(file).stat().st_size)
                headers["Content-Type"] = "text/plain; charset=utf-8" if Path(file).suffix == ".txt" else "application/octet-stream"
            request = Request(url, data=data, headers=headers, method=method)
            with self.opener.open(request, timeout=60) as response:
                body = response.read()
                return body if binary else json.loads(body)
        except HTTPError as error:
            # Do not echo headers, credentials, response body or signed download URLs.
            raise GitHubError(error.code) from None
        finally:
            if stream is not None:
                stream.close()

    def list_releases(self, repo):
        releases, page = [], 1
        while True:
            batch = self.request("GET", f"/repos/{repo}/releases?per_page=100&page={page}")
            releases.extend(batch)
            if len(batch) < 100:
                return releases
            page += 1

    def create_release(self, repo, payload):
        return self.request("POST", f"/repos/{repo}/releases", payload)

    def get_release(self, repo, release_id):
        return self.request("GET", f"/repos/{repo}/releases/{release_id}")

    def list_assets(self, repo, release_id):
        assets, page = [], 1
        while True:
            batch = self.request("GET", f"/repos/{repo}/releases/{release_id}/assets?per_page=100&page={page}")
            assets.extend(batch)
            if len(batch) < 100:
                return assets
            page += 1

    def upload_asset(self, release, file):
        url = release["upload_url"].split("{", 1)[0] + "?" + urlencode({"name": Path(file).name})
        return self.request("POST", url, file=file)

    def download_asset(self, repo, asset_id):
        return self.request("GET", f"/repos/{repo}/releases/assets/{asset_id}", binary=True)

    def publish(self, repo, release_id):
        return self.request("PATCH", f"/repos/{repo}/releases/{release_id}", {"draft": False})


def product_slug(value):
    value = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    value = value.encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value or len(value) > 80:
        raise ValueError("Tên sản phẩm cần 1–80 ký tự sau khi bỏ dấu và chuẩn hóa.")
    return value


def version_number(value):
    if str(value) == "auto":
        return None
    if not re.fullmatch(r"[0-9]+", str(value)) or int(value) < 1:
        raise ValueError("Version phải là auto hoặc số nguyên dương.")
    return int(value)


def check_repo(repo):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GitHub repo phải ở dạng owner/repo.")


def publish_txt(txt, repo, product, version="auto", metadata=None, state_dir=None, client=None, now=None):
    check_repo(repo)
    product = product_slug(product)
    explicit = version_number(version)
    txt = Path(txt).resolve()
    txt.read_text(encoding="utf-8")  # Validate encoding without changing any bytes.
    if txt.stat().st_size >= 2 * 1024**3:
        raise ValueError("TXT phải nhỏ hơn 2 GiB để đính kèm GitHub Release.")
    digest = sha256(txt)
    metadata = metadata or {}
    metadata_digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    owner = repo.split("/", 1)[0]
    prefix = f"ocr-{owner}-{product}-v"
    state = Path(state_dir) if state_dir else txt.parent / ".github_releases" / f"{owner}_{repo.split('/')[1]}_{product}_{digest[:12]}"
    state.mkdir(parents=True, exist_ok=True)
    plan_path = state / "plan.json"
    pending = state / "upload_pending.json"
    try:
        client = client or GitHubClient()
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if (plan["repo"], plan["product"], plan["txt_sha256"], plan["metadata_sha256"]) != (repo, product, digest, metadata_digest):
                raise ValueError("Gói phát hành đã đổi; dùng thư mục state mới, không ghi đè bản cũ.")
            if explicit is not None and plan["version"] != explicit:
                raise ValueError("Gói này đã gắn với version khác; tạo gói xuất mới để phát hành version mới.")
        else:
            releases = client.list_releases(repo)
            pattern = re.compile(re.escape(prefix) + r"([0-9]+)$")
            used = [int(match[1]) for release in releases if (match := pattern.fullmatch(release["tag_name"]))]
            number = explicit or max(used, default=0) + 1
            if number in used:
                raise ValueError("Version đã có trên GitHub; không ghi đè. Chọn auto hoặc số mới.")
            stamp = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
            plan = {"repo": repo, "product": product, "account": owner, "version": number,
                    "created_at_vietnam": stamp.isoformat(), "timezone": "Asia/Ho_Chi_Minh",
                    "timestamp": stamp.strftime("%H%M%S_%Y-%m-%d"),
                    "txt_sha256": digest, "metadata_sha256": metadata_digest,
                    "publication_id": uuid.uuid4().hex}
            write_json(plan_path, plan)
        # Reserve the numeric version with a unique tag. A concurrent publisher
        # cannot claim the same version even when its timestamp differs.
        for _ in range(10):
            number = plan["version"]
            tag = prefix + f"{number:04d}"
            marker = f"<!-- han-ocr:{plan['publication_id']} -->"
            releases = client.list_releases(repo)
            release = next((item for item in releases if item["tag_name"] == tag), None)
            if release is not None:
                if marker in (release.get("body") or ""):
                    break
                if explicit is not None:
                    raise ValueError("Version đã thuộc gói khác; không ghi đè.")
                taken = [int(m[1]) for item in releases if (m := re.fullmatch(re.escape(prefix) + r"([0-9]+)", item["tag_name"]))]
                plan["version"] = max(taken, default=number) + 1
                write_json(plan_path, plan)
                continue
            base = f"{owner}_{product}_v{number:04d}_{plan['timestamp']}"
            pages = metadata.get("scope_pages", [])
            body = (f"Văn bản trích xuất thô, chưa hiệu đính.\n\nPhạm vi trang PDF: {pages or 'xem manifest'}. "
                    f"Đủ toàn bộ sách: {bool(metadata.get('complete_book'))}.\n\n"
                    f"SHA-256 TXT: `{digest}`\n\nThời gian Việt Nam: {plan['created_at_vietnam']}.\n\n{marker}")
            try:
                release = client.create_release(repo, {"tag_name": tag, "name": base,
                    "body": body, "draft": True, "prerelease": not metadata.get("complete_book", False)})
                break
            except GitHubError as error:
                if error.status != 422 or explicit is not None:
                    raise
                # Re-read the server on a race; never overwrite a release.
        else:
            raise ValueError("Không giữ được số phiên bản sau 10 lần; chạy lại để tiếp tục.")
        base = f"{owner}_{product}_v{plan['version']:04d}_{plan['timestamp']}"
        assets_dir = state / "assets"
        assets_dir.mkdir(exist_ok=True)
        target = assets_dir / (base + ".txt")
        shutil.copyfile(txt, target)
        release_manifest = dict(metadata, release={**plan, "tag": release["tag_name"], "txt_filename": target.name})
        manifest_path = assets_dir / (base + ".manifest.json")
        write_json(manifest_path, release_manifest)
        checksum_path = assets_dir / (base + ".sha256")
        write_text(checksum_path, "".join(f"{sha256(p)}  {p.name}\n" for p in (target, manifest_path)))
        expected = (target, manifest_path, checksum_path)
        existing = {asset["name"]: asset for asset in client.list_assets(repo, release["id"])}
        uploaded = []
        for path in expected:
            asset = existing.get(path.name)
            if asset is None:
                if not release["draft"]:
                    raise ValueError("Release đã công khai nhưng thiếu asset; không sửa bản đã phát hành.")
                asset = client.upload_asset(release, path)
            remote = client.download_asset(repo, asset["id"])
            if hashlib.sha256(remote).hexdigest() != sha256(path):
                raise ValueError("Asset không khớp SHA-256; giữ bản nháp, không ghi đè dữ liệu remote.")
            uploaded.append({"name": path.name, "sha256": sha256(path), "url": asset["browser_download_url"]})
            print("GitHub verified:", path.name, flush=True)
        if release["draft"]:
            release = client.publish(repo, release["id"])
        confirmed = client.get_release(repo, release["id"])
        if confirmed["draft"]:
            raise ValueError("Release vẫn là bản nháp; chạy lại để tiếp tục.")
        # Draft assets can have temporary /untagged-... URLs. Resolve the
        # canonical download URLs again after publication, never cache those.
        published_assets = {asset["name"]: asset for asset in client.list_assets(repo, release["id"])}
        for item in uploaded:
            if item["name"] not in published_assets:
                raise ValueError("Release công khai thiếu asset đã xác minh; chạy lại bước xuất.")
            item["url"] = published_assets[item["name"]]["browser_download_url"]
        receipt = {"repo": repo, "release_url": confirmed["html_url"], "tag": release["tag_name"],
                   "version": plan["version"], "created_at_vietnam": plan["created_at_vietnam"],
                   "txt_filename": target.name, "txt_url": uploaded[0]["url"], "assets": uploaded,
                   "complete_book": bool(metadata.get("complete_book")), "quality_reviewed": False}
        write_json(state / "receipt.json", receipt)
        if pending.exists():
            pending.unlink()
        print("TXT đã xuất:", receipt["txt_url"], flush=True)
        return receipt
    except Exception as error:
        write_json(pending, {"repo": repo, "error_type": type(error).__name__})
        raise


def publish_bundle(bundle, repo, product="an-quang-van-sao-zh", version="auto", client=None):
    from export_results import validate_bundle
    bundle = Path(bundle).resolve()
    validate_bundle(bundle)
    metadata = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    return publish_txt(bundle / "han.txt", repo, product, version, metadata,
                       state_dir=bundle / "github_release", client=client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path)
    source.add_argument("--txt", type=Path)
    source.add_argument("--check-auth", action="store_true")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--product", default="an-quang-van-sao-zh")
    parser.add_argument("--version", default="auto")
    parser.add_argument("--metadata", type=Path, help="Metadata JSON khi xuất một TXT có sẵn.")
    parser.add_argument("--state-dir", type=Path, help="Lưu kế hoạch/receipt để upload lại cùng bản.")
    args = parser.parse_args()
    try:
        check_repo(args.repo)
        if args.check_auth:
            GitHubClient().request("GET", f"/repos/{args.repo}")
            print("GitHub: đã xác thực và đọc được repo. Quyền ghi được kiểm tra khi tạo bản nháp.")
        elif args.bundle:
            publish_bundle(args.bundle, args.repo, args.product, args.version)
        else:
            metadata = json.loads(args.metadata.read_text(encoding="utf-8")) if args.metadata else None
            publish_txt(args.txt, args.repo, args.product, args.version, metadata, args.state_dir)
    except Exception as error:
        # Credentials and upstream request details must never enter notebook output.
        message = str(error) if isinstance(error, (GitHubError, ValueError)) else type(error).__name__
        print(f"Chưa xuất được GitHub Release: {message}. TXT vẫn được giữ trên Drive/máy. "
              "Chạy lại bước xuất để tiếp tục, không cần OCR lại.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
