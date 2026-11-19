"""Trợ lý osetup: tiến trình chạy ngầm (không cửa sổ) trên máy người dùng.

- Lắng nghe CHỈ ở 127.0.0.1:47890; trang web osetup (đúng địa chỉ đã cho phép) nói chuyện với nó để
  dò phần mềm đã cài và bấm "Cài ngay" mà không cần dán lệnh.
- Chỉ nhận id có trong danh mục osetup (không chạy lệnh tuỳ ý).
- Tự khởi động cùng máy (Task Scheduler / autostart), có mục gỡ trong "Installed apps" của Windows.
Lệnh:  osetup assistant install | run | status | uninstall
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import core

VERSION = "1.0"
PORT = 47890
HOME = Path.home() / ".osetup"
CONF = HOME / "assistant.json"
LOG = HOME / "assistant.log"
DEFAULT_ORIGINS = ["http://localhost", "http://127.0.0.1"]  # + các origin được thêm lúc cài (--origin)
TASK = "osetup-assistant"
UNINST_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\osetup-assistant"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _log(msg: str) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def allowed_origins() -> list[str]:
    try:
        return json.loads(CONF.read_text(encoding="utf-8")).get("origins", DEFAULT_ORIGINS)
    except Exception:
        return DEFAULT_ORIGINS


def origin_ok(origin: str | None) -> bool:
    if not origin:  # curl / ứng dụng cục bộ
        return True
    o = origin.rstrip("/")
    return any(o == a.rstrip("/") or (a.startswith("http://") and o.startswith(a.rstrip("/") + ":")) for a in allowed_origins())


# ------------------------------------------------------------------ tác vụ
class State:
    apps, profiles = core.load_data()
    env = core.detect_env()
    jobs: dict[str, dict] = {}
    lock = threading.Lock()


def scan() -> list[str]:
    env = State.env
    items = [core.Item(i, a, core.resolve(a, env)) for i, a in State.apps.items() if a.get("kind") != "selfhost"]
    return sorted(core.find_present(items, env))


def start_install(ids: list[str], dry_run: bool) -> str:
    bad = [i for i in ids if i not in State.apps or State.apps[i].get("kind") == "selfhost"]
    if bad:
        raise ValueError("id không có trong danh mục: " + ", ".join(bad[:5]))
    jid = uuid.uuid4().hex[:8]
    job = {"id": jid, "status": "queued", "log": [], "results": [], "manual": []}
    State.jobs[jid] = job

    def work():
        with State.lock:  # mỗi lần chỉ một tiến trình cài
            job["status"] = "running"
            items = core.make_items(State.apps, ids, State.env)
            for it in items:
                if it.action and it.action.manager == "manual":
                    job["manual"].append({"id": it.id, "name": it.app["name"], "url": it.action.pkg})
            auto = [it for it in items if not it.action or it.action.manager != "manual"]
            emit = lambda s: job["log"].append(str(s))  # noqa: E731
            try:
                if not State.env.managers and not dry_run:
                    emit("Không thấy trình quản lý gói (winget/brew/apt).")
                    job["status"] = "failed"
                    return
                res = core.run_items(auto, State.env, dry_run=dry_run, emit=emit)
                job["results"] = [list(r) for r in res]
                job["status"] = "failed" if any(r[1] == "failed" for r in res) else "done"
            except Exception as e:  # noqa: BLE001
                emit(f"Lỗi: {e}")
                job["status"] = "failed"
            _log(f"job {jid} {job['status']} ({len(auto)} mục)")

    threading.Thread(target=work, daemon=True).start()
    return jid


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    server_version = "osetup-assistant"

    def log_message(self, *a):  # im lặng
        pass

    def _cors(self):
        o = self.headers.get("Origin")
        if o and origin_ok(o):
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Headers", "content-type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not origin_ok(self.headers.get("Origin")):
            return self._send(403, {"error": "origin không được phép"})
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not origin_ok(self.headers.get("Origin")):
            return self._send(403, {"error": "origin không được phép"})
        p = self.path.split("?")[0]
        if p == "/status":
            return self._send(200, {"ok": True, "assistant": True, "version": VERSION, "os": State.env.os,
                                    "managers": State.env.managers, "apps": len(State.apps)})
        if p == "/scan":
            return self._send(200, {"installed": scan()})
        if p == "/updates":
            txt = core._capture(["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity"]) if "winget" in State.env.managers else ""
            return self._send(200, {"text": txt})
        if p.startswith("/job/"):
            j = State.jobs.get(p[5:])
            return self._send(200 if j else 404, j or {"error": "không có job"})
        self._send(404, {"error": "không có"})

    def do_POST(self):
        if not origin_ok(self.headers.get("Origin")):
            return self._send(403, {"error": "origin không được phép"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n < 200_000 else {}
        except ValueError:
            body = {}
        p = self.path.split("?")[0]
        if p == "/install":
            try:
                ids = [str(i) for i in body.get("ids", [])][:300]
                return self._send(200, {"job": start_install(ids, bool(body.get("dry_run")))})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
        if p == "/uninstall-stop":  # chỉ cho tiến trình cục bộ (không có Origin)
            if self.headers.get("Origin"):
                return self._send(403, {"error": "không được phép"})
            self._send(200, {"ok": True})
            threading.Thread(target=lambda: State.srv.shutdown(), daemon=True).start()  # type: ignore[attr-defined]
            return
        if p == "/uninstall":
            self._send(200, {"ok": True, "msg": "Đang gỡ trợ lý…"})
            threading.Thread(target=lambda: (time.sleep(0.5), uninstall()), daemon=True).start()
            return
        self._send(404, {"error": "không có"})


def run() -> int:
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        _log("cổng đã bận — trợ lý đang chạy rồi")
        return 0
    _log(f"trợ lý {VERSION} chạy ở 127.0.0.1:{PORT}")
    State.srv = srv  # type: ignore[attr-defined]
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ------------------------------------------------------------------ cài / gỡ
def _app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _launcher() -> list[str]:
    """Lệnh chạy ngầm trợ lý (Windows dùng pythonw để không hiện cửa sổ)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "assistant", "run"]
    py = sys.executable
    if platform.system() == "Windows":
        w = Path(py).with_name("pythonw.exe")
        py = str(w) if w.exists() else py
    return [py, str(_app_dir() / "osetup_main.py"), "assistant", "run"]


def _q(parts: list[str]) -> str:
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def install(origins: list[str] | None = None) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    merged = list(dict.fromkeys(DEFAULT_ORIGINS + allowed_origins() + [o.rstrip("/") for o in (origins or []) if o]))
    CONF.write_text(json.dumps({"origins": merged}, indent=1), encoding="utf-8")
    print("Trang web được phép điều khiển trợ lý:", ", ".join(merged))
    cmd = _launcher()
    sysname = platform.system()
    if sysname == "Windows":
        subprocess.run(["schtasks", "/Create", "/TN", TASK, "/TR", _q(cmd), "/SC", "ONLOGON", "/RL", "LIMITED", "/F"],
                       creationflags=NOWIN, capture_output=True)
        unst = _q(cmd[:-2] + ["assistant", "uninstall"])
        for name, typ, val in (("DisplayName", "REG_SZ", "osetup — Trợ lý cài phần mềm"), ("Publisher", "REG_SZ", "osetup"),
                               ("DisplayVersion", "REG_SZ", VERSION), ("UninstallString", "REG_SZ", unst),
                               ("InstallLocation", "REG_SZ", str(_app_dir()))):
            subprocess.run(["reg", "add", UNINST_KEY, "/v", name, "/t", typ, "/d", val, "/f"], creationflags=NOWIN, capture_output=True)
        subprocess.Popen(cmd, creationflags=NOWIN | getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
    elif sysname == "Darwin":
        pl = Path.home() / "Library/LaunchAgents/vn.osetup.assistant.plist"
        pl.parent.mkdir(parents=True, exist_ok=True)
        args = "".join(f"<string>{a}</string>" for a in cmd)
        pl.write_text(f'<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key><string>vn.osetup.assistant</string>'
                      f"<key>ProgramArguments</key><array>{args}</array><key>RunAtLoad</key><true/></dict></plist>")
        subprocess.run(["launchctl", "load", str(pl)], capture_output=True)
    else:
        d = Path.home() / ".config/autostart"
        d.mkdir(parents=True, exist_ok=True)
        (d / "osetup-assistant.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName=osetup assistant\nExec={_q(cmd)}\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print("Đã cài trợ lý osetup (chạy ngầm, tự khởi động cùng máy). Gỡ: osetup assistant uninstall")
    return 0


def _stop_running() -> None:
    try:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/uninstall-stop", method="POST", data=b"{}"), timeout=2)
    except Exception:
        pass
    if platform.system() == "Windows":
        # dự phòng: tìm tiến trình đang giữ cổng rồi tắt
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, creationflags=NOWIN).stdout
        for ln in out.splitlines():
            if f"127.0.0.1:{PORT}" in ln and "LISTENING" in ln:
                pid = ln.split()[-1]
                if pid != str(os.getpid()):
                    subprocess.run(["taskkill", "/F", "/PID", pid], creationflags=NOWIN, capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "osetup_main.py assistant run"], capture_output=True)


def uninstall() -> int:
    sysname = platform.system()
    if sysname == "Windows":
        subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], creationflags=NOWIN, capture_output=True)
        subprocess.run(["reg", "delete", UNINST_KEY, "/f"], creationflags=NOWIN, capture_output=True)
    elif sysname == "Darwin":
        pl = Path.home() / "Library/LaunchAgents/vn.osetup.assistant.plist"
        subprocess.run(["launchctl", "unload", str(pl)], capture_output=True)
        pl.unlink(missing_ok=True)
    else:
        (Path.home() / ".config/autostart/osetup-assistant.desktop").unlink(missing_ok=True)
    app = _app_dir()
    managed = app.name == "app" and app.parent.name in ("osetup-assistant", ".osetup-assistant")
    if sysname == "Windows" and managed and not getattr(sys, "frozen", False):
        subprocess.Popen(f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{app}"', shell=True, creationflags=NOWIN)
    elif managed:
        shutil.rmtree(app, ignore_errors=True)
    _stop_running()
    print("Đã gỡ trợ lý osetup.")
    return 0


def status() -> int:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/status", timeout=2) as r:
            print("Trợ lý đang chạy:", r.read().decode())
        return 0
    except Exception:
        print("Trợ lý không chạy.")
        return 1


def main(action: str, origins: list[str] | None = None) -> int:
    if action == "install":
        return install(origins)
    return {"run": run, "uninstall": uninstall, "status": status}[action]()
