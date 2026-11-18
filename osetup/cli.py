"""Giao diện dòng lệnh của osetup."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core


def _csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _plan(args, apps, profiles, env):
    selected = list(args.profiles)
    if getattr(args, "everything", False):
        selected = ["all"]
    ids, selfhost = core.build_plan(
        apps, profiles, selected, include_optional=getattr(args, "all", False),
        include_popular=getattr(args, "popular", False),
        only=_csv(getattr(args, "only", None)), skip=_csv(getattr(args, "skip", None)),
        with_base=not getattr(args, "no_base", False),
        with_runtimes=not getattr(args, "no_runtimes", False))
    items = core.make_items(apps, ids, env, getattr(args, "prefer", None))
    if getattr(args, "env_only", False):
        items = [i for i in items if core.kind_of(i.app) == "runtime"]
    if getattr(args, "apps_only", False):
        items = [i for i in items if core.kind_of(i.app) == "app"]
    return items, selfhost


def _print_plan(items, selfhost, apps, env, present=frozenset()):
    print(f"Hệ điều hành: {env.os} | trình quản lý gói: {', '.join(env.managers) or '(không có!)'}")
    for kind in ("runtime", "app"):
        group = [i for i in items if core.kind_of(i.app) == kind]
        if not group:
            continue
        print(f"\n══ {core.KIND_LABEL[kind]} ({len(group)}) ══")
        for it in group:
            how = f"{it.action.manager}:{it.action.pkg}" if it.action else "— không hỗ trợ —"
            mark = "✓" if it.id in present else "•"
            note = "  (ĐÃ CÀI — bỏ qua)" if it.id in present else ""
            print(f"  {mark} {it.app['name']:<34} {it.app['desc']:<46} [{how}]{note}")
    tags = [it.action.manager for it in items if it.action] + (["✓ đã cài"] if present else []) \
        + (["không hỗ trợ"] if any(not it.action for it in items) else []) \
        + (["không mở nguồn"] if any(it.app.get("popular") for it in items) else [])
    legend = core.legend_for(tags)
    if legend:
        print("\nChú giải:")
        for k, v in legend:
            print(f"  {k:<15} {v}")
    todo = [i for i in items if i.id not in present and i.action]
    print(f"\nTổng: {len(items)} mục — đã có sẵn: {len(present)}, cần cài: {len(todo)}")
    if selfhost:
        print("\n══ GỢI Ý TỰ TRIỂN KHAI (self-host, không cài tự động) ══")
        for sid in selfhost:
            a = apps[sid]
            print(f"  ◦ {a['name']:<18} {a['desc']}  → {a['url']}")


def cmd_list(args, apps, profiles, env):
    print(f"{'all':<14} ★ TẤT CẢ các nhóm (dùng: osetup install all)\n")
    for pid, p in profiles.items():
        print(f"{pid:<14} {p['name']}\n{'':<14} {p['desc']}")
        print(f"{'':<14} core: {len(p.get('core', []))}, optional: {len(p.get('optional', []))}, "
              f"self-host: {len(p.get('selfhost', []))}")


def cmd_show(args, apps, profiles, env):
    args.all = args.popular = True
    items, selfhost = _plan(args, apps, profiles, env)
    _print_plan(items, selfhost, apps, env)


def _scan_present(args, items, env):
    if getattr(args, "force", False):
        return set()
    print("Đang quét phần mềm đã cài trên máy...")
    return core.find_present(items, env)


def cmd_install(args, apps, profiles, env):
    items, selfhost = _plan(args, apps, profiles, env)
    present = _scan_present(args, items, env)
    _print_plan(items, selfhost, apps, env, present)
    if not [i for i in items if i.id not in present and i.action]:
        print("\nKhông có gì cần cài.")
        return 0
    if env.os == "windows" and not env.managers and not args.dry_run and core.ensure_winget():
        env = core.detect_env()
        items = core.make_items(apps, [i.id for i in items], env, getattr(args, "prefer", None))
    if not env.managers and not args.dry_run:
        print("\nKhông tìm thấy trình quản lý gói (winget/brew/apt/flatpak). Dùng --dry-run hoặc cài winget/brew trước.")
        return 2
    if not args.dry_run and not args.yes:
        if input("\nTiến hành cài đặt? [y/N] ").strip().lower() not in ("y", "yes", "c", "co", "có"):
            print("Đã huỷ.")
            return 1
    res = core.run_items(items, env, dry_run=args.dry_run, present=present)
    rc = core.summarize(res)
    if not args.dry_run:
        print(f"Log: {core.write_log(res)}")
    return rc


def cmd_check(args, apps, profiles, env):
    """Chỉ kiểm tra: mục nào đã có, mục nào còn thiếu (không cài gì)."""
    args.all = args.popular = getattr(args, "all", False)
    items, selfhost = _plan(args, apps, profiles, env)
    present = _scan_present(args, items, env)
    _print_plan(items, [], apps, env, present)


def cmd_legend(args, apps, profiles, env):
    for k, v in core.LEGEND.items():
        print(f"{k:<16} {v}")


def cmd_discover(args, apps, profiles, env):
    """Quét GitHub: top-N repo nhiều sao theo chủ đề (vd: osetup discover crm --top 20)."""
    if args.list_presets:
        for slug, (label, q) in core.DISCOVER_PRESETS.items():
            print(f"{slug:<12} {label:<34} ({q})")
        return 0
    query = " ".join(args.query) or "selfhost"
    try:
        rows = core.discover(query, args.top, language=args.lang)
    except RuntimeError as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 2
    print(f"Top {len(rows)} repo GitHub nhiều sao nhất cho: {core.resolve_query(query)}\n")
    for n, r in enumerate(rows, 1):
        print(f"{n:>3}. ★ {r['stars']:>8,}  {r['full_name']:<44} [{r['license']}] cập nhật {r['updated']}")
        if r["desc"]:
            print(f"       {r['desc'][:110]}")
        print(f"       {r['url']}")
    if args.save and rows:
        print(f"\nĐã lưu {len(rows)} repo vào {core.save_selfhost(rows)} (nhóm 'my-selfhost')")
    return 0


def cmd_pack(args, apps, profiles, env):
    """Chế độ 2 (bước 1): tải installer về thư mục gói offline."""
    if env.os != "windows" and not args.dry_run:
        print("Chế độ offline hiện chỉ hỗ trợ Windows (dùng `winget download`). Thêm --dry-run để xem trước.")
        return 2
    items, _ = _plan(args, apps, profiles, env)
    _print_plan(items, [], apps, env)
    if env.os == "windows" and not args.dry_run and not core.ensure_winget():
        return 2
    res = core.pack_items(items, args.dir, dry_run=args.dry_run)
    rc = core.summarize(res)
    if not args.dry_run:
        print(f"\nGói offline: {args.dir}\nMang cả thư mục sang máy đích rồi chạy install-offline.bat")
    return rc


def cmd_offline_install(args, apps, profiles, env):
    """Chế độ 2 (bước 2): cài từ gói offline, không cần mạng."""
    pack = core.load_pack(args.dir)
    print(f"Gói tạo lúc {pack['created']} — {len(pack['items'])} mục")
    if not args.dry_run and not args.yes:
        if input("Tiến hành cài từ gói offline? [y/N] ").strip().lower() not in ("y", "yes", "c", "có"):
            print("Đã huỷ.")
            return 1
    res = core.run_pack(args.dir, only=_csv(args.only), skip=_csv(args.skip), dry_run=args.dry_run,
                        skip_installed=not args.force)
    return core.summarize(res)


def cmd_export(args, apps, profiles, env):
    items, _ = _plan(args, apps, profiles, env)
    out = Path(args.out or ("osetup-install.ps1" if env.os == "windows" else "osetup-install.sh"))
    out.write_text(core.export_script(items, env), encoding="utf-8")
    print(f"Đã ghi {out} ({len(items)} mục)")


def cmd_stars(args, apps, profiles, env):
    args.all = True
    args.profiles = args.profiles or [p for p in profiles if p not in core.BASE_PROFILES]
    ids, selfhost = core.build_plan(apps, profiles, args.profiles, include_optional=True, include_popular=True)
    rows = [(apps[i]["name"], apps[i]["repo"]) for i in ids + selfhost if apps[i].get("repo")]
    stars = core.fetch_stars([r for _, r in rows])
    for name, repo in sorted(rows, key=lambda x: -(stars.get(x[1]) or -1)):
        s = stars.get(repo)
        print(f"{'?' if s is None else f'{s:,}':>9} ★  {name:<24} github.com/{repo}")


def cmd_verify(args, apps, profiles, env):
    args.all = args.popular = True
    args.profiles = args.profiles or list(profiles)
    items, _ = _plan(args, apps, profiles, env)
    bad = 0
    for it in items:
        a = it.action
        if not a or a.manager == "manual":
            continue
        ok = core.exists_in_repo(a)
        bad += not ok
        print(f"{'OK     ' if ok else 'THIẾU  '} {a.manager}:{a.pkg}  ({it.app['name']})")
    print(f"\n{bad} gói không tìm thấy — sửa ID trong catalog.json hoặc ~/.osetup/custom.json." if bad else "\nTất cả ID hợp lệ.")
    return 1 if bad else 0


def cmd_gui(args, apps, profiles, env):
    from .gui import run_gui
    run_gui(apps, profiles, env)


def cmd_menu(args, apps, profiles, env):
    return interactive(apps, profiles, env)


def interactive(apps, profiles, env):
    print("Chọn chế độ:\n 1. Online: chọn → tải → cài ngay\n 2. Tạo gói offline (chỉ tải về, cài sau)\n"
          " 3. Cài từ gói offline đã tải")
    mode = input("Chế độ [1]: ").strip() or "1"
    if mode == "3":
        d = input("Thư mục gói offline [.]: ").strip() or "."
        ns = argparse.Namespace(dir=d, only=None, skip=None, dry_run=False, yes=False, force=False)
        return cmd_offline_install(ns, apps, profiles, env)
    ids = [p for p in profiles if p not in core.BASE_PROFILES]
    print("\nChọn nhóm đối tượng (nhập số, cách nhau bằng dấu cách):\n")
    print("  0. ★ TẤT CẢ các nhóm")
    for n, pid in enumerate(ids, 1):
        print(f" {n:>2}. {profiles[pid]['name']} — {profiles[pid]['desc']}")
    raw = input("\nLựa chọn: ").split()
    try:
        chosen = ["all"] if "0" in raw else [ids[int(x) - 1] for x in raw]
    except (ValueError, IndexError):
        print("Lựa chọn không hợp lệ.")
        return 1
    ns = argparse.Namespace(profiles=chosen, all=input("Cài cả phần mềm tuỳ chọn? [y/N] ").lower() == "y",
                            popular=input("Cài cả phần mềm miễn phí không mở nguồn (Zalo, Chrome…)? [y/N] ").lower() == "y",
                            only=None, skip=None, no_base=False, no_runtimes=False, prefer=None,
                            env_only=False, apps_only=False, dry_run=False, yes=False, everything=False, force=False)
    if mode == "2":
        ns.dir = input("Thư mục lưu gói offline [osetup-pack]: ").strip() or "osetup-pack"
        return cmd_pack(ns, apps, profiles, env)
    return cmd_install(ns, apps, profiles, env)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="osetup", description="Thiết lập phần mềm ban đầu theo nhóm người dùng (ưu tiên mã nguồn mở)")
    p.add_argument("--profile-file", action="append", default=[], help="JSON bổ sung app/profile tuỳ chỉnh")
    p.add_argument("--target", choices=["windows", "macos", "linux"], help="giả lập OS khác (dry-run/export)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="liệt kê profile")
    s = sub.add_parser("show", help="xem chi tiết profile (gồm optional)")
    s.add_argument("profiles", nargs="+")

    def add_install_opts(sp):
        sp.add_argument("profiles", nargs="*", default=[])
        sp.add_argument("--all", action="store_true", help="gồm cả phần mềm optional")
        sp.add_argument("--only", help="chỉ các app id này (phẩy)")
        sp.add_argument("--skip", help="bỏ các app id này (phẩy)")
        sp.add_argument("--popular", action="store_true", help="gồm cả phần mềm miễn phí nhưng không mở nguồn (Chrome, Zalo, Zoom…)")
        sp.add_argument("--everything", action="store_true", help="chọn TẤT CẢ các nhóm")
        sp.add_argument("--env-only", action="store_true", help="chỉ phần MÔI TRƯỜNG (runtime/SDK)")
        sp.add_argument("--apps-only", action="store_true", help="chỉ PHẦN MỀM (bỏ môi trường)")
        sp.add_argument("--no-base", action="store_true", help="không kèm profile base")
        sp.add_argument("--no-runtimes", action="store_true", help="không kèm VC++/.NET/Java/DirectX…")
        sp.add_argument("--prefer", choices=["apt", "flatpak"], help="Linux: ưu tiên trình quản lý gói")

    s = sub.add_parser("install", help="CHẾ ĐỘ 1 — chọn → tải → cài (online)")
    add_install_opts(s)
    s.add_argument("--force", action="store_true", help="không kiểm tra, cài cả mục đã có")
    s.add_argument("-n", "--dry-run", action="store_true")
    s.add_argument("-y", "--yes", action="store_true", help="không hỏi xác nhận")
    for name, h in (("pack", "CHẾ ĐỘ 2 — tải sẵn installer thành gói offline (Windows)"),
                    ("download", "(bí danh của pack)")):
        s = sub.add_parser(name, help=h)
        add_install_opts(s)
        s.add_argument("-d", "--dir", default="osetup-pack")
        s.add_argument("-n", "--dry-run", action="store_true")
    s = sub.add_parser("offline-install", help="CHẾ ĐỘ 2 — cài từ gói offline, không cần mạng")
    s.add_argument("-d", "--dir", default=".")
    s.add_argument("--only"); s.add_argument("--skip")
    s.add_argument("--force", action="store_true", help="cài cả mục đã có")
    s.add_argument("-n", "--dry-run", action="store_true")
    s.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("legend", help="giải thích các thẻ: winget, apt, manual, ✓ đã cài…")
    s = sub.add_parser("discover", help="quét GitHub: top-N repo nhiều sao theo chủ đề (self-host, crm, erp…)")
    s.add_argument("query", nargs="*", help="preset (xem --list-presets) hoặc truy vấn tự do, vd: crm | 'invoice language:php'")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--lang", help="lọc theo ngôn ngữ lập trình")
    s.add_argument("--save", action="store_true", help="lưu kết quả vào nhóm my-selfhost")
    s.add_argument("--list-presets", action="store_true")
    s = sub.add_parser("check", help="kiểm tra mục nào đã cài / còn thiếu (không cài gì)")
    add_install_opts(s)
    s = sub.add_parser("export", help="xuất script .ps1/.sh để xem trước / mang đi máy khác")
    add_install_opts(s)
    s.add_argument("-o", "--out")
    s = sub.add_parser("stars", help="xếp hạng theo sao GitHub (cần mạng)")
    s.add_argument("profiles", nargs="*")
    s = sub.add_parser("verify", help="kiểm tra ID gói có tồn tại trong kho không")
    s.add_argument("profiles", nargs="*")
    sub.add_parser("gui", help="mở giao diện đồ hoạ")
    sub.add_parser("menu", help="menu văn bản tương tác")

    args = p.parse_args(argv)
    try:
        apps, profiles = core.load_data(args.profile_file)
        env = core.detect_env(args.target)
        if not args.cmd:
            if env.os == "windows":  # nhấp đúp osetup.exe → GUI, lỗi thì dùng menu
                try:
                    return cmd_gui(args, apps, profiles, env) or 0
                except Exception as e:
                    print(f"Không mở được GUI ({e}), chuyển sang menu văn bản.")
            return interactive(apps, profiles, env) if sys.stdin.isatty() else p.print_help() or 0
        fn = {"list": cmd_list, "show": cmd_show, "install": cmd_install, "export": cmd_export,
              "check": cmd_check, "legend": cmd_legend, "discover": cmd_discover, "pack": cmd_pack, "download": cmd_pack, "offline-install": cmd_offline_install,
              "menu": cmd_menu,
              "stars": cmd_stars, "verify": cmd_verify, "gui": cmd_gui}[args.cmd]
        return fn(args, apps, profiles, env) or 0
    except KeyError as e:
        print(f"Lỗi: {e.args[0]}", file=sys.stderr)
        return 2
