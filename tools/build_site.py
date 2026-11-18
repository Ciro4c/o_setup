"""Sinh docs/index.html: trang web chạy được (chọn nhóm -> tick -> tải script cài đặt).
Chạy:  python tools/build_site.py   (dữ liệu lấy từ osetup/data/*.json)"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from osetup import core  # noqa: E402

KEEP = ("name", "desc", "license", "repo", "winget", "brew", "cask", "apt", "flatpak",
        "manual", "kind", "popular", "quiet", "url")

apps, profiles = core.load_data()
data = {
    "apps": {k: {f: v[f] for f in KEEP if f in v} for k, v in apps.items()},
    "profiles": profiles,
    "legend": core.LEGEND,
    "presets": {k: [v[0], v[1]] for k, v in core.DISCOVER_PRESETS.items()},
}
html = (ROOT / "tools" / "site_template.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
(ROOT / "docs" / ".nojekyll").write_text("")
print("docs/index.html:", len(html) // 1024, "KB;", len(apps), "ứng dụng;", len(profiles), "nhóm")
