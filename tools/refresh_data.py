"""Cào dữ liệu GitHub: top-N theo từng chủ đề + số sao của mọi repo trong danh mục.
Chạy tự động bởi .github/workflows/refresh.yml (dùng GITHUB_TOKEN); chạy tay: python tools/refresh_data.py
Ghi: osetup/data/top.json, osetup/data/stars_cache.json (nếu lỗi mạng thì giữ dữ liệu cũ)."""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from osetup import core  # noqa: E402

TOP = int(os.environ.get("TOP_N", "20"))
DATA = ROOT / "osetup" / "data"


def load(name):
    f = DATA / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    pause = 2.5 if token else 7  # tránh giới hạn tần suất của search API

    top = load("top.json")
    ok = 0
    for slug, (label, _q) in core.DISCOVER_PRESETS.items():
        try:
            rows = core.discover(slug, TOP)
            top[slug] = {"label": label, "updated": now, "items": rows}
            ok += 1
            print(f"✓ top {len(rows):>2} · {label}")
        except Exception as e:  # giữ bản cũ
            print(f"! {label}: {e}")
        time.sleep(pause)
    (DATA / "top.json").write_text(json.dumps(top, ensure_ascii=False, indent=1), encoding="utf-8")

    apps, _ = core.load_data()
    repos = sorted({a["repo"] for a in apps.values() if a.get("repo")})
    stars = load("stars_cache.json")
    got = 0
    for repo in repos:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "osetup"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                stars[repo] = json.load(r)["stargazers_count"]
            got += 1
        except Exception as e:
            print(f"! {repo}: {e}")
    stars["_updated"] = now
    (DATA / "stars_cache.json").write_text(json.dumps(stars, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Top: {ok}/{len(core.DISCOVER_PRESETS)} chủ đề · Sao: {got}/{len(repos)} repo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
