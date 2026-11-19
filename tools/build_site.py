"""Sinh docs/index.html: trang web chạy được (chọn nhóm -> tick -> tải script cài đặt).
Chạy:  python tools/build_site.py   (dữ liệu lấy từ osetup/data/*.json)"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from osetup import core  # noqa: E402

def detect_repo() -> str:
    """owner/repo của chính repo này: biến GITHUB_REPOSITORY (Actions) > git remote origin."""
    import os
    import re
    import subprocess
    r = os.environ.get("GITHUB_REPOSITORY")
    if not r:
        try:
            url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", url)
            r = f"{m.group(1)}/{m.group(2)}" if m else ""
        except OSError:
            r = ""
    return r or "Ciro4c/o_setup-phan_mem_ban_dau-"


REPO = detect_repo()
OWNER, NAME = REPO.split("/", 1)
BASE = f"https://{OWNER.lower()}.github.io/" + ("" if NAME.lower() == f"{OWNER.lower()}.github.io" else NAME + "/")

KEEP = ("name", "desc", "license", "repo", "winget", "brew", "cask", "apt", "flatpak",
        "manual", "kind", "popular", "quiet", "url")

apps, profiles = core.load_data()
data = {
    "apps": {k: {f: v[f] for f in KEEP if f in v} for k, v in apps.items()},
    "profiles": profiles,
    "legend": core.LEGEND,
    "top": json.loads((ROOT / "osetup/data/top.json").read_text(encoding="utf-8") or "{}"),
    "stars": json.loads((ROOT / "osetup/data/stars_cache.json").read_text(encoding="utf-8") or "{}"),
    "default_base": BASE,
    "repo": REPO,
    "presets": {k: [v[0], v[1]] for k, v in core.DISCOVER_PRESETS.items()},
}
html = (ROOT / "tools" / "site_template.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
(ROOT / "docs" / ".nojekyll").write_text("")
for f in ("install.ps1", "install.sh", "assistant.ps1", "assistant.sh"):
    text = (ROOT / "tools" / "bootstrap" / f).read_text(encoding="utf-8").replace("__REPO__", REPO)
    (ROOT / "docs" / f).write_text(text, encoding="utf-8", newline="\n" if f.endswith(".sh") else None)
print("repo:", REPO, "→", BASE)
print("docs/index.html:", len(html) // 1024, "KB;", len(apps), "ứng dụng;", len(profiles), "nhóm")
