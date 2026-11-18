"""Lõi của osetup: nạp dữ liệu, phát hiện hệ điều hành, lập kế hoạch và cài đặt."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

DATA_DIR = Path(__file__).resolve().parent / "data"
USER_DIR = Path.home() / ".osetup"
Emit = Callable[[str], None]


# ----------------------------------------------------------------- dữ liệu
def _read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_data(extra_files: Iterable[str] = ()) -> tuple[dict, dict]:
    """Trả về (apps, profiles). Hợp nhất ~/.osetup/custom.json và các file --profile-file."""
    apps: dict = {}
    for f in sorted(DATA_DIR.glob("catalog*.json")):
        apps.update(_read(f)["apps"])
    profiles = _read(DATA_DIR / "profiles.json")["profiles"]
    files = list(extra_files)
    candidates = [USER_DIR / "custom.json"]
    if getattr(sys, "frozen", False):  # file custom.json đặt cạnh osetup.exe
        candidates.insert(0, Path(sys.executable).parent / "custom.json")
    files = [c for c in candidates if c.exists()] + files
    for f in files:
        d = _read(f)
        apps.update(d.get("apps", {}))
        profiles.update(d.get("profiles", {}))
    return apps, profiles


# ------------------------------------------------------------ môi trường
@dataclass
class Env:
    os: str                 # windows | macos | linux
    managers: list[str]     # winget | brew | apt | flatpak


def detect_env(target: str | None = None) -> Env:
    """target: ép giả lập hệ điều hành khác (dùng cho dry-run / export)."""
    if target:
        return Env(target, {"windows": ["winget"], "macos": ["brew"],
                            "linux": ["apt", "flatpak"]}[target])
    system = platform.system()
    if system == "Windows":
        return Env("windows", ["winget"] if shutil.which("winget") else [])
    if system == "Darwin":
        return Env("macos", ["brew"] if shutil.which("brew") else [])
    mgrs = [m for m, exe in (("apt", "apt-get"), ("flatpak", "flatpak")) if shutil.which(exe)]
    return Env("linux", mgrs)


@dataclass
class Action:
    manager: str            # winget | brew | cask | apt | flatpak | manual
    pkg: str                # id gói, hoặc URL nếu manual


def resolve(app: dict, env: Env, prefer: str | None = None) -> Action | None:
    if app.get("kind") == "selfhost":
        return None
    if env.os == "windows":
        if "winget" in env.managers and app.get("winget"):
            return Action("winget", app["winget"])
    elif env.os == "macos":
        if "brew" in env.managers:
            if app.get("cask"):
                return Action("cask", app["cask"])
            if app.get("brew"):
                return Action("brew", app["brew"])
    else:
        order = [prefer] if prefer else []
        order += [m for m in ("apt", "flatpak") if m not in order]
        for m in order:
            if m in env.managers and app.get(m):
                return Action(m, app[m])
    url = app.get("manual", {}).get(env.os)
    return Action("manual", url) if url else None


def _sudo() -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() != 0 and shutil.which("sudo"):
        return ["sudo"]
    return []


def command(a: Action) -> list[str]:
    if a.manager == "winget":
        return ["winget", "install", "--id", a.pkg, "-e", "--silent",
                "--accept-package-agreements", "--accept-source-agreements"]
    if a.manager == "brew":
        return ["brew", "install", a.pkg]
    if a.manager == "cask":
        return ["brew", "install", "--cask", a.pkg]
    if a.manager == "apt":
        return _sudo() + ["apt-get", "install", "-y", a.pkg]
    if a.manager == "flatpak":
        return ["flatpak", "install", "-y", "--noninteractive", "flathub", a.pkg]
    raise ValueError(a.manager)


def check_command(a: Action) -> list[str] | None:
    """Lệnh kiểm tra gói tồn tại trong kho (dùng cho `verify`)."""
    return {
        "winget": ["winget", "show", "--id", a.pkg, "-e", "--accept-source-agreements"],
        "brew": ["brew", "info", a.pkg],
        "cask": ["brew", "info", "--cask", a.pkg],
        "apt": ["apt-cache", "show", a.pkg],
        "flatpak": ["flatpak", "remote-info", "flathub", a.pkg],
    }.get(a.manager)


def installed_command(a: Action) -> list[str] | None:
    return {
        "winget": ["winget", "list", "--id", a.pkg, "-e", "--accept-source-agreements"],
        "brew": ["brew", "list", a.pkg],
        "cask": ["brew", "list", "--cask", a.pkg],
        "apt": ["dpkg", "-s", a.pkg],
        "flatpak": ["flatpak", "info", a.pkg],
    }.get(a.manager)


def _ok(cmd: list[str] | None) -> bool:
    if not cmd or not shutil.which(cmd[0]):
        return False
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120).returncode == 0
    except Exception:
        return False


def _capture(cmd: list[str], timeout=120) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="ignore", timeout=timeout)
        return r.stdout or ""
    except Exception:
        return ""


def _real_os() -> str:
    return {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")


def scan_installed(env: Env) -> dict:
    """Quét MỘT lần toàn bộ gói đang có trên máy (nhanh hơn hỏi từng gói)."""
    scan: dict = {"winget": "", "apt": set(), "flatpak": set(), "brew": set(), "cask": set()}
    if "winget" in env.managers:
        scan["winget"] = _capture(["winget", "list", "--accept-source-agreements",
                                   "--disable-interactivity"]).lower()
    if "apt" in env.managers:
        for line in _capture(["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\n"]).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("ii"):
                scan["apt"].add(parts[0].lower())
    if "flatpak" in env.managers:
        scan["flatpak"] = {l.strip().lower() for l in
                           _capture(["flatpak", "list", "--columns=application"]).splitlines() if l.strip()}
    if "brew" in env.managers:
        scan["brew"] = {l.strip().lower() for l in _capture(["brew", "list", "--formula", "-1"]).splitlines()}
        scan["cask"] = {l.strip().lower() for l in _capture(["brew", "list", "--cask", "-1"]).splitlines()}
    return scan


def is_present_action(a: Action | None, scan: dict) -> bool:
    if a is None or a.manager == "manual":
        return False
    pkg = a.pkg.lower()
    if a.manager == "winget":
        pat = r"(?<![\w.+\-])" + re.escape(pkg) + r"(?![\w.+\-])"
        return bool(re.search(pat, scan.get("winget", "")))
    return pkg in scan.get(a.manager, set())


def is_present(item: "Item", scan: dict, env: Env) -> bool:
    b = item.app.get("bin")
    if b and env.os == _real_os() and shutil.which(b):  # cài ngoài trình quản lý gói
        return True
    return is_present_action(item.action, scan)


def find_present(items: list["Item"], env: Env, scan: dict | None = None) -> set[str]:
    """Id các mục đã có trên máy (để bỏ qua, tránh cài trùng)."""
    scan = scan if scan is not None else scan_installed(env)
    return {it.id for it in items if is_present(it, scan, env)}


def is_installed(a: Action) -> bool:
    return _ok(installed_command(a))


def exists_in_repo(a: Action) -> bool:
    return _ok(check_command(a))


# ---------------------------------------------------------------- kế hoạch
BASE_PROFILES = ("base", "runtimes")


def build_plan(apps: dict, profiles: dict, selected: list[str], *, include_optional=False,
               include_popular=False, only: Iterable[str] = (), skip: Iterable[str] = (),
               with_base=True, with_runtimes=True):
    """Trả về (app_ids, selfhost_ids) đã bỏ trùng, giữ thứ tự.

    base/runtimes được kèm theo ở dạng chỉ-core (trừ khi chọn trực tiếp)."""
    only, skip = set(only), set(skip)
    if "all" in selected:  # "all" = tất cả nhóm (trừ base/runtimes vốn đã kèm sẵn)
        rest = [p for p in profiles if p not in BASE_PROFILES]
        selected = rest + [p for p in selected if p != "all" and p not in rest]
    pre = [p for p, on in (("base", with_base), ("runtimes", with_runtimes)) if on and p not in selected]
    ids = pre + list(selected)
    ordered, selfhost = [], []
    for pid in ids:
        if pid not in profiles:
            raise KeyError(f"Không có profile '{pid}'. Dùng `osetup list` để xem danh sách.")
        p = profiles[pid]
        names = list(p.get("core", []))
        if include_optional:
            names += p.get("optional", [])
        if include_popular:
            names += p.get("popular", [])
        for aid in names:
            if aid not in apps:
                raise KeyError(f"Profile '{pid}' tham chiếu app không tồn tại: {aid}")
            if aid in skip or (only and aid not in only) or aid in ordered:
                continue
            ordered.append(aid)
        for aid in p.get("selfhost", []):
            if aid not in selfhost:
                selfhost.append(aid)
    return ordered, selfhost


KIND_LABEL = {"runtime": "MÔI TRƯỜNG (runtime / SDK / toolchain)", "app": "PHẦN MỀM"}


def kind_of(app: dict) -> str:
    return "runtime" if app.get("kind") == "runtime" else "app"


@dataclass
class Item:
    id: str
    app: dict
    action: Action | None


def make_items(apps: dict, ids: list[str], env: Env, prefer: str | None = None) -> list[Item]:
    items = [Item(i, apps[i], resolve(apps[i], env, prefer)) for i in ids]
    # mục "quiet" (riêng cho 1 OS) không có trên OS này thì ẩn đi cho gọn
    items = [it for it in items if it.action or not it.app.get("quiet")]
    items.sort(key=lambda it: kind_of(it.app) != "runtime")  # môi trường cài trước, phần mềm sau
    return items


def ensure_winget(emit: Emit = print) -> bool:
    """Windows: nếu thiếu winget thì thử cài App Installer qua PowerShell."""
    if shutil.which("winget"):
        return True
    emit("Không thấy winget — đang thử cài App Installer...")
    ps = ("$p=\"$env:TEMP\\appinstaller.msixbundle\"; "
          "Invoke-WebRequest https://aka.ms/getwinget -OutFile $p; Add-AppxPackage $p")
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=True)
    except Exception as e:
        emit(f"Không cài được winget tự động ({e}). Cập nhật 'App Installer' trong Microsoft Store rồi chạy lại.")
        return False
    return bool(shutil.which("winget"))



# ----------------------------------------------------------------- thực thi
_WINGET_ALREADY = {0x8A15002B, 0x8A150061, 0x8A15002B - 2**32, 0x8A150061 - 2**32}


def run_items(items: list[Item], env: Env, *, dry_run=False, emit: Emit = print,
              skip_installed=True, present: set | None = None) -> list[tuple[str, str, str]]:
    """Cài từng mục, không dừng khi một mục lỗi. Trả về [(id, trạng thái, ghi chú)]."""
    results: list[tuple[str, str, str]] = []
    if present is None:  # quét 1 lần cho cả danh sách (nhanh hơn hỏi từng gói)
        present = find_present(items, env) if skip_installed else set()
    if not dry_run and env.os == "linux" and "apt" in env.managers:
        emit("› apt-get update")
        subprocess.run(_sudo() + ["apt-get", "update"])
    total = len(items)
    for n, it in enumerate(items, 1):
        tag = f"[{n}/{total}] {it.app['name']}"
        a = it.action
        if a is None:
            emit(f"{tag}: không hỗ trợ trên {env.os} (bỏ qua)")
            results.append((it.id, "unsupported", env.os))
            continue
        if a.manager == "manual":
            emit(f"{tag}: cần cài thủ công → {a.pkg}")
            results.append((it.id, "manual", a.pkg))
            continue
        if it.id in present:
            emit(f"{tag}: đã cài sẵn — bỏ qua")
            results.append((it.id, "present", a.pkg))
            continue
        cmd = command(a)
        if dry_run:
            emit(f"{tag}: $ {' '.join(cmd)}")
            results.append((it.id, "dry-run", " ".join(cmd)))
            continue
        emit(f"{tag}: đang cài ({a.manager}:{a.pkg}) ...")
        try:
            rc = subprocess.run(cmd).returncode
        except FileNotFoundError:
            rc = 127
        if rc == 0:
            emit(f"{tag}: xong")
            results.append((it.id, "installed", a.pkg))
        elif a.manager == "winget" and rc in _WINGET_ALREADY:
            emit(f"{tag}: winget báo đã có / không cần cập nhật")
            results.append((it.id, "present", a.pkg))
        else:
            emit(f"{tag}: LỖI (mã {rc})")
            results.append((it.id, "failed", f"{a.manager}:{a.pkg} rc={rc}"))
    return results


def summarize(results, emit: Emit = print) -> int:
    groups: dict[str, list[str]] = {}
    for i, st, _ in results:
        groups.setdefault(st, []).append(i)
    labels = {"downloaded": "Đã tải", "installed": "Đã cài", "present": "Đã có sẵn (bỏ qua)", "failed": "Lỗi", "manual": "Cài thủ công",
              "unsupported": "Không hỗ trợ OS này", "dry-run": "Dry-run"}
    emit("\n── Tổng kết ──")
    for st, label in labels.items():
        if st in groups:
            emit(f"{label} ({len(groups[st])}): {', '.join(groups[st])}")
    return 1 if "failed" in groups else 0


def write_log(results) -> Path:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    p = USER_DIR / f"install-{time.strftime('%Y%m%d-%H%M%S')}.log"
    p.write_text("\n".join("\t".join(r) for r in results), encoding="utf-8")
    return p


# ------------------------------------------------------------------ xuất script
def export_script(items: list[Item], env: Env) -> str:
    win = env.os == "windows"
    lines = ["# Sinh bởi osetup — kiểm tra rồi chạy" if win else "#!/usr/bin/env bash\n# Sinh bởi osetup — kiểm tra rồi chạy"]
    if not win:
        lines.append("set -u")
        if env.os == "linux" and "apt" in env.managers:
            lines.append("sudo apt-get update")
    for it in items:
        a = it.action
        lines.append(f"# {it.app['name']} — {it.app['desc']}")
        if a is None:
            lines.append(f"# (không hỗ trợ {env.os})")
        elif a.manager == "manual":
            lines.append(f"# Cài thủ công: {a.pkg}")
        else:
            lines.append(" ".join(command(a)))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- GitHub stars
def fetch_stars(repos: Iterable[str], emit: Emit = print) -> dict[str, int | None]:
    """Lấy số sao từ GitHub API, cache 24h tại ~/.osetup/stars.json. Đặt GITHUB_TOKEN để tránh giới hạn."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = USER_DIR / "stars.json"
    cache = _read(cache_file) if cache_file.exists() else {}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    out: dict[str, int | None] = {}
    now = time.time()
    for repo in repos:
        c = cache.get(repo)
        if c and now - c["t"] < 86400:
            out[repo] = c["stars"]
            continue
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}",
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "osetup"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                stars = json.load(r)["stargazers_count"]
            cache[repo] = {"stars": stars, "t": now}
            out[repo] = stars
        except Exception as e:  # mạng / rate limit
            emit(f"  ! {repo}: {e}")
            out[repo] = None
    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    return out


# ============================================================ CHẾ ĐỘ OFFLINE
# Bước 1 (có mạng):  pack_items()  → tải installer bằng `winget download` + ghi pack.json
# Bước 2 (không mạng): run_pack()  → chạy từng installer ở chế độ silent
PACK_FILE = "pack.json"
_PACK_EXTS = {".yaml", ".yml"}
_DEFAULT_SILENT = {
    "inno": ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
    "nullsoft": ["/S"],
    "burn": ["/quiet", "/norestart"],
    "wix": ["/quiet", "/norestart"],
}


def _unquote(v: str) -> str:
    return v.strip().strip("'\"")


def inspect_download(d: Path) -> dict:
    """Đọc thư mục do `winget download` tạo: tên installer, loại, tham số cài ngầm."""
    files = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() not in _PACK_EXTS]
    text = "".join(f.read_text(encoding="utf-8", errors="ignore")
                   for f in d.iterdir() if f.suffix.lower() in _PACK_EXTS)
    installer = max(files, key=lambda f: f.stat().st_size).name if files else None
    t = re.search(r"^\s*(?:-\s*)?InstallerType:\s*(\S+)", text, re.M)
    s = re.search(r"^\s*Silent:\s*(.+?)\s*$", text, re.M)
    return {"installer": installer,
            "type": _unquote(t.group(1)).lower() if t else "",
            "silent": _unquote(s.group(1)).split() if s else []}


def installer_cmd(entry: dict, path: str) -> list[str] | None:
    """Lệnh cài ngầm cho một installer đã tải. None = không tự cài được (zip/portable...)."""
    ext = Path(path).suffix.lower()
    t = entry.get("type", "")
    if ext == ".msi":
        return ["msiexec", "/i", path, "/qn", "/norestart"]
    if ext in (".msix", ".msixbundle", ".appx", ".appxbundle"):
        return ["powershell", "-NoProfile", "-Command", f"Add-AppxPackage -Path '{path}'"]
    if ext == ".exe":
        return [path] + (entry.get("silent") or _DEFAULT_SILENT.get(t, ["/S"]))
    return None


def pack_items(items: list[Item], dest: str, emit: Emit = print, dry_run=False):
    """Tải toàn bộ installer vào `dest` (mỗi app một thư mục) và ghi pack.json."""
    dest_p = Path(dest)
    results, entries, manual = [], [], []
    todo = [it for it in items if it.action]
    for n, it in enumerate(todo, 1):
        a = it.action
        tag = f"[{n}/{len(todo)}] {it.app['name']}"
        if a.manager == "manual":
            emit(f"{tag}: không tải tự động được → {a.pkg}")
            manual.append({"name": it.app["name"], "url": a.pkg})
            results.append((it.id, "manual", a.pkg))
            continue
        if a.manager != "winget":
            emit(f"{tag}: chế độ offline chỉ hỗ trợ winget (Windows) — bỏ qua")
            results.append((it.id, "unsupported", a.manager))
            continue
        d = dest_p / it.id
        cmd = ["winget", "download", "--id", a.pkg, "-e", "-d", str(d),
               "--accept-package-agreements", "--accept-source-agreements"]
        if dry_run:
            emit(f"{tag}: $ {' '.join(cmd)}")
            results.append((it.id, "dry-run", " ".join(cmd)))
            continue
        emit(f"{tag}: đang tải ...")
        try:
            rc = subprocess.run(cmd).returncode
        except FileNotFoundError:
            rc = 127
        info = inspect_download(d) if rc == 0 and d.is_dir() else {}
        if info.get("installer"):
            entries.append({"id": it.id, "name": it.app["name"], "kind": kind_of(it.app),
                            "pkg": a.pkg, "dir": it.id, **info})
            results.append((it.id, "downloaded", a.pkg))
        else:
            emit(f"{tag}: LỖI tải (mã {rc})")
            results.append((it.id, "failed", a.pkg))
    if not dry_run:
        dest_p.mkdir(parents=True, exist_ok=True)
        (dest_p / PACK_FILE).write_text(json.dumps(
            {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "items": entries, "manual": manual},
            ensure_ascii=False, indent=2), encoding="utf-8")
        finalize_pack(dest_p, manual)
    return results


def finalize_pack(dest: Path, manual: list[dict]) -> None:
    """Chép chương trình vào gói để mang sang máy khác là chạy được ngay."""
    bat = ["@echo off", "chcp 65001 >nul", "cd /d \"%~dp0\""]
    if getattr(sys, "frozen", False):
        shutil.copy2(sys.executable, dest / "osetup.exe")
        bat.append('osetup.exe offline-install -d "%~dp0"')
    else:
        src = dest / "osetup_src"
        shutil.copytree(Path(__file__).resolve().parent, src / "osetup", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        bat.append('set PYTHONPATH=%~dp0osetup_src')
        bat.append('python -m osetup offline-install -d "%~dp0"')
    bat.append("pause")
    (dest / "install-offline.bat").write_text("\r\n".join(bat) + "\r\n", encoding="utf-8")
    if manual:
        (dest / "CAI-THU-CONG.txt").write_text(
            "Các phần mềm sau không tải tự động được, hãy tải tay:\n" +
            "\n".join(f"- {m['name']}: {m['url']}" for m in manual) + "\n", encoding="utf-8")


def load_pack(dest: str) -> dict:
    f = Path(dest) / PACK_FILE
    if not f.exists():
        raise KeyError(f"Không thấy {PACK_FILE} trong '{dest}'. Hãy tạo gói bằng `osetup pack` trước.")
    return _read(f)


def run_pack(dest: str, *, only: Iterable[str] = (), skip: Iterable[str] = (), dry_run=False,
             emit: Emit = print, skip_installed=True) -> list[tuple[str, str, str]]:
    """Cài từ gói offline (không cần mạng). Môi trường cài trước, phần mềm sau."""
    only, skip = set(only), set(skip)
    entries = [e for e in load_pack(dest)["items"]
               if e["id"] not in skip and (not only or e["id"] in only)]
    entries.sort(key=lambda e: e.get("kind") != "runtime")
    scan = scan_installed(Env("windows", ["winget"])) if skip_installed else {}
    results = []
    for n, e in enumerate(entries, 1):
        tag = f"[{n}/{len(entries)}] {e['name']}"
        path = str(Path(dest) / e["dir"] / e["installer"])
        cmd = installer_cmd(e, path)
        if cmd is None:
            emit(f"{tag}: loại '{e.get('type') or Path(path).suffix}' cần giải nén/cài tay → {path}")
            results.append((e["id"], "manual", path))
            continue
        if skip_installed and is_present_action(Action("winget", e["pkg"]), scan):
            emit(f"{tag}: đã cài sẵn — bỏ qua")
            results.append((e["id"], "present", e["pkg"]))
            continue
        if dry_run:
            emit(f"{tag}: $ {' '.join(cmd)}")
            results.append((e["id"], "dry-run", " ".join(cmd)))
            continue
        emit(f"{tag}: đang cài ...")
        try:
            rc = subprocess.run(cmd).returncode
        except FileNotFoundError:
            rc = 127
        ok = rc in (0, 3010)  # 3010 = cần khởi động lại
        emit(f"{tag}: {'xong' if ok else f'LỖI (mã {rc})'}")
        results.append((e["id"], "installed" if ok else "failed", f"rc={rc}"))
    return results


# ============================================================ CHÚ GIẢI (legend)
LEGEND = {
    "winget": "Trình quản lý gói chính thức của Windows 10/11. Tự tải & cài ngầm từ kho Microsoft bằng `winget install --id <ID>`.",
    "brew": "Homebrew — trình quản lý gói dòng lệnh của macOS (và Linux).",
    "cask": "Homebrew Cask — cài ứng dụng có giao diện trên macOS (.app).",
    "apt": "Trình quản lý gói của Debian/Ubuntu (`apt-get install`). Cần quyền sudo; bản có thể cũ hơn.",
    "flatpak": "Gói ứng dụng chạy sandbox dùng được trên mọi bản Linux (kho Flathub). Bản thường mới hơn apt.",
    "manual": "Không cài tự động được — cần tải & cài tay theo đường dẫn đi kèm.",
    "không hỗ trợ": "Chưa có gói cho hệ điều hành này; mục sẽ bị bỏ qua.",
    "không mở nguồn": "Miễn phí hoặc thương mại nhưng mã nguồn đóng (ví dụ Chrome, Zalo, Zoom). Mặc định không cài.",
    "✓ đã cài": "Máy đã có phần mềm này (quét trước khi cài) — được bỏ qua để tránh cài trùng.",
    "MÔI TRƯỜNG": "Thư viện / runtime / SDK mà phần mềm khác cần để chạy hoặc để lập trình (VC++, .NET, Java, Python, Git…).",
    "PHẦN MỀM": "Ứng dụng người dùng cuối (Firefox, GIMP, LibreOffice…).",
    "self-host": "Phần mềm dạng máy chủ (Odoo, Nextcloud…) tự dựng bằng Docker/VPS; không cài tự động, chỉ gợi ý kèm link repo.",
    "dry-run": "Chạy thử: in ra lệnh sẽ chạy nhưng không cài gì.",
    "★": "Số sao (stars) trên GitHub — thước đo độ phổ biến của repo.",
}


def legend_for(tags: Iterable[str]) -> list[tuple[str, str]]:
    """Chú giải cho các thẻ xuất hiện (khớp theo từ đầu của thẻ)."""
    seen, out = set(), []
    for t in tags:
        for key in LEGEND:
            if t.startswith(key) and key not in seen:
                seen.add(key)
                out.append((key, LEGEND[key]))
    return out


def tooltip_for(app: dict, action: "Action | None", env_os: str) -> str:
    """Nội dung tooltip khi rê chuột vào một mục."""
    lines = [f"{app['name']} — {app['desc']}"]
    if action:
        lines.append(f"Cách cài: {action.manager}" + (f" (gói: {action.pkg})" if action.manager != "manual" else f" → {action.pkg}"))
        lines.append(LEGEND.get(action.manager, ""))
    else:
        lines.append(f"Không có gói cho {env_os}.")
    if app.get("license"):
        lines.append(f"Giấy phép: {app['license']}")
    if app.get("repo"):
        lines.append(f"Repo: github.com/{app['repo']}")
    if app.get("popular"):
        lines.append(LEGEND["không mở nguồn"])
    return "\n".join(l for l in lines if l)


# ============================================================ KHÁM PHÁ GITHUB
# slug -> (nhãn hiển thị, truy vấn GitHub search)
DISCOVER_PRESETS: dict[str, tuple[str, str]] = {
    "selfhost": ("Self-hosted — tất cả", "topic:self-hosted"),
    "crm": ("CRM / chăm sóc khách hàng", "topic:crm"),
    "erp": ("ERP", "topic:erp"),
    "accounting": ("Kế toán / hoá đơn", "topic:accounting"),
    "pm": ("Quản lý dự án / Kanban", "topic:project-management"),
    "wiki": ("Wiki / ghi chú / tài liệu", "topic:wiki"),
    "bi": ("Phân tích / BI / dashboard", "topic:business-intelligence"),
    "chat": ("Chat / họp / cộng tác", "topic:chat topic:self-hosted"),
    "automation": ("Tự động hoá quy trình", "topic:automation topic:self-hosted"),
    "llm": ("AI / LLM chạy cục bộ", "topic:llm topic:self-hosted"),
    "password": ("Quản lý mật khẩu", "topic:password-manager"),
    "photos": ("Ảnh / media / phát phim", "topic:self-hosted topic:media"),
    "monitoring": ("Giám sát / DevOps", "topic:monitoring topic:self-hosted"),
}


def resolve_query(text: str) -> str:
    """Nhận slug preset, nhãn preset, hoặc truy vấn tự do (vd 'invoice language:php')."""
    t = (text or "").strip()
    for slug, (label, q) in DISCOVER_PRESETS.items():
        if t.lower() in (slug, label.lower()):
            return q
    return t or DISCOVER_PRESETS["selfhost"][1]


def discover(query: str, top: int = 20, *, language: str | None = None) -> list[dict]:
    """Tìm top-N repo GitHub nhiều sao nhất theo truy vấn. Đặt GITHUB_TOKEN để tăng giới hạn."""
    q = f"{resolve_query(query)} archived:false"
    if language:
        q += f" language:{language}"
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": q, "sort": "stars", "order": "desc", "per_page": max(1, min(int(top), 100))})
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "osetup"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RuntimeError("GitHub đang giới hạn tần suất (chưa đăng nhập: 10 lượt tìm/phút). "
                               "Đặt biến môi trường GITHUB_TOKEN rồi thử lại.") from e
        raise RuntimeError(f"GitHub trả lỗi HTTP {e.code}") from e
    except Exception as e:
        raise RuntimeError(f"Không kết nối được GitHub: {e}") from e
    return [{"full_name": it["full_name"], "stars": it["stargazers_count"],
             "desc": (it.get("description") or "").strip(), "url": it["html_url"],
             "license": (it.get("license") or {}).get("spdx_id") or "?",
             "language": it.get("language") or "", "updated": (it.get("pushed_at") or "")[:10]}
            for it in data.get("items", [])]


def save_selfhost(results: list[dict], profile_id: str = "my-selfhost") -> Path:
    """Lưu kết quả khám phá vào ~/.osetup/custom.json (nhóm 'Của tôi') để lần sau hiện trong gợi ý."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    f = USER_DIR / "custom.json"
    data = _read(f) if f.exists() else {}
    data.setdefault("apps", {})
    prof = data.setdefault("profiles", {}).setdefault(
        profile_id, {"name": "Của tôi (self-host đã lưu)", "desc": "Repo lưu từ lệnh discover", "core": [], "selfhost": []})
    for r in results:
        aid = "sh-" + re.sub(r"[^a-z0-9]+", "-", r["full_name"].lower()).strip("-")
        data["apps"][aid] = {"kind": "selfhost", "name": r["full_name"].split("/")[1], "desc": r["desc"][:110] or "(không mô tả)",
                             "repo": r["full_name"], "license": r["license"], "url": r["url"]}
        if aid not in prof["selfhost"]:
            prof["selfhost"].append(aid)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f
