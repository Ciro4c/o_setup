"""Giao diện đồ hoạ tkinter với 3 chế độ:

1. Online:             chọn nhóm → chọn môi trường/phần mềm → tải & cài ngay
2. Tạo gói offline:    chọn như trên → chỉ tải về một thư mục (winget download)
3. Cài từ gói offline: chọn thư mục gói đã tải → cài không cần mạng

- Mọi khu gom gọn được bằng [-]/[+]; có khu "Chú giải" giải thích winget/apt/manual…;
  rê chuột lên một mục để xem tooltip chi tiết (cách cài, giấy phép, repo).
- Mục đã có trên máy được quét trước, đánh dấu "✓ đã cài" và tự bỏ chọn.
- Khu "Gợi ý tự triển khai" có nút "Quét GitHub": top-N repo nhiều sao theo chủ đề.
"""
from __future__ import annotations

import queue
import threading
import webbrowser

from . import core

SCAN_DONE = "\0scan-done"


def run_gui(apps: dict, profiles: dict, env: core.Env) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    root = tk.Tk()
    root.title("osetup — Thiết lập phần mềm ban đầu")
    root.geometry("1180x800")

    mode = tk.StringVar(value="online")
    folder = tk.StringVar(value="osetup-pack")
    dry = tk.BooleanVar(value=False)
    force = tk.BooleanVar(value=False)
    all_var = tk.BooleanVar(value=False)
    topic_var = tk.StringVar(value=core.DISCOVER_PRESETS["selfhost"][0])
    top_var = tk.StringVar(value="20")
    pvars = {pid: tk.BooleanVar() for pid in profiles if pid not in core.BASE_PROFILES}
    avars: dict[str, tk.BooleanVar] = {}
    collapsed: dict[str, bool] = {"legend": True}
    state = {"scan": None, "scanning": False, "disc": [], "disc_msg": "", "stars": {}}
    q: queue.Queue = queue.Queue()

    # ------------------------------------------------------------ tooltip
    class Tip:
        def __init__(self, widget, text):
            self.w, self.text, self.tw = widget, text, None
            widget.bind("<Enter>", self.show, add="+")
            widget.bind("<Leave>", self.hide, add="+")

        def show(self, _=None):
            if self.tw or not self.text:
                return
            self.tw = tk.Toplevel(self.w)
            self.tw.wm_overrideredirect(True)
            self.tw.wm_geometry(f"+{self.w.winfo_rootx() + 30}+{self.w.winfo_rooty() + 22}")
            tk.Label(self.tw, text=self.text, justify="left", background="#ffffe1", relief="solid",
                     borderwidth=1, wraplength=460, padx=6, pady=4).pack()

        def hide(self, _=None):
            if self.tw:
                self.tw.destroy()
                self.tw = None

    # ------------------------------------------------------------ chế độ + thư mục
    top = ttk.LabelFrame(root, text="Chế độ")
    top.pack(fill="x", padx=8, pady=6)
    for val, txt in (("online", "1. Online: chọn → tải → cài ngay"),
                     ("pack", "2. Tạo gói offline (chỉ tải về, cài sau)"),
                     ("offline", "3. Cài từ gói offline đã tải")):
        ttk.Radiobutton(top, text=txt, value=val, variable=mode,
                        command=lambda: refresh(True)).pack(side="left", padx=10, pady=4)

    frow = ttk.Frame(root)
    frow.pack(fill="x", padx=8)
    ttk.Label(frow, text="Thư mục gói offline:").pack(side="left")
    entry = ttk.Entry(frow, textvariable=folder, width=60)
    entry.pack(side="left", padx=6)

    def browse():
        d = filedialog.askdirectory()
        if d:
            folder.set(d)
            refresh(True)
    ttk.Button(frow, text="Chọn…", command=browse).pack(side="left")
    rescan_btn = ttk.Button(frow, text="Quét lại máy", command=lambda: rescan())
    rescan_btn.pack(side="right")
    Tip(rescan_btn, "Quét lại các phần mềm đang cài trên máy (winget list / dpkg / flatpak / brew) "
                    "để đánh dấu '✓ đã cài' và tránh cài trùng.")

    # ------------------------------------------------------------ thân
    body = ttk.Frame(root)
    body.pack(fill="both", expand=True, padx=8, pady=6)
    left = ttk.LabelFrame(body, text="Nhóm đối tượng")
    left.pack(side="left", fill="y")
    right = ttk.Frame(body)
    right.pack(side="left", fill="both", expand=True, padx=(8, 0))

    canvas = tk.Canvas(right, highlightthickness=0)
    sb = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    def toggle_all():
        for v in pvars.values():
            v.set(all_var.get())
        refresh(False)

    def on_profile():
        all_var.set(all(v.get() for v in pvars.values()))
        refresh(False)

    ttk.Checkbutton(left, text="★ TẤT CẢ các nhóm", variable=all_var,
                    command=toggle_all).pack(anchor="w", padx=8, pady=(6, 2))
    ttk.Separator(left).pack(fill="x", padx=6, pady=2)
    for pid, v in pvars.items():
        cb = ttk.Checkbutton(left, text=profiles[pid]["name"], variable=v, command=on_profile)
        cb.pack(anchor="w", padx=8, pady=2)
        Tip(cb, profiles[pid]["desc"])
    ttk.Label(left, text=f"\nHệ điều hành: {env.os}\nTrình quản lý gói:\n{', '.join(env.managers) or 'không có'}",
              justify="left").pack(anchor="w", padx=8)

    # ------------------------------------------------------------ quét máy (nền)
    def rescan():
        if state["scanning"]:
            return
        state["scanning"], state["scan"] = True, None
        q.put("Đang quét phần mềm đã cài trên máy...")

        def work():
            state["scan"] = core.scan_installed(env)
            state["scanning"] = False
            q.put(SCAN_DONE)
        threading.Thread(target=work, daemon=True).start()

    def present_ids(rows) -> set[str]:
        scan = state["scan"]
        return set() if scan is None else {r["id"] for r in rows if r["present"](scan)}

    # ------------------------------------------------------------ quét GitHub (nền)
    def run_discover():
        try:
            n = max(1, min(int(top_var.get()), 100))
        except ValueError:
            n = 20
        query = topic_var.get()
        state["disc_msg"] = f"Đang quét GitHub: top {n} cho '{core.resolve_query(query)}' ..."
        refresh(False)

        def work():
            try:
                q.put(("disc", core.discover(query, n), None))
            except Exception as e:
                q.put(("disc", [], str(e)))
        threading.Thread(target=work, daemon=True).start()

    def save_disc():
        if not state["disc"]:
            q.put("Chưa có kết quả để lưu — bấm 'Quét GitHub' trước.")
            return
        f = core.save_selfhost(state["disc"])
        q.put(f"Đã lưu {len(state['disc'])} repo vào {f} — xuất hiện ở nhóm 'Của tôi' lần mở sau.")

    def fetch_suggestion_stars(repos):
        state["disc_msg"] = "Đang lấy số sao ..."
        refresh(False)

        def work():
            q.put(("stars", core.fetch_stars(repos, emit=lambda m: None), None))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ dữ liệu từng chế độ
    def build_rows():
        m = mode.get()
        if m == "offline":
            try:
                pack = core.load_pack(folder.get())
            except Exception as e:
                q.put(f"! {e}")
                return [], []
            rows = []
            for e in pack["items"]:
                act = core.Action("winget", e["pkg"])
                rows.append({"id": e["id"], "name": e["name"], "desc": "", "kind": e["kind"],
                             "how": "gói offline", "default": True, "ok": True, "group": "Trong gói offline",
                             "tip": f"{e['name']}\nInstaller đã tải sẵn (loại: {e['type'] or 'không rõ'}).\n"
                                    f"Gói winget gốc: {e['pkg']}\nSẽ cài ngầm không cần mạng.",
                             "present": (lambda sc, a=act: core.is_present_action(a, sc))})
            return rows, []
        chosen = [p for p, v in pvars.items() if v.get()]  # rỗng vẫn hiện base + runtimes (luôn kèm theo)
        core_ids, _ = core.build_plan(apps, profiles, chosen)
        all_ids, selfhost = core.build_plan(apps, profiles, chosen, include_optional=True, include_popular=True)
        origin: dict[str, str] = {}
        for pid in list(core.BASE_PROFILES) + chosen:      # mỗi app xếp vào nhóm đầu tiên chứa nó
            p = profiles[pid]
            for aid in p.get("core", []) + p.get("optional", []) + p.get("popular", []):
                origin.setdefault(aid, p["name"])
        rows = []
        for it in core.make_items(apps, all_ids, env):
            a = it.action
            how = a.manager if a else "không hỗ trợ"
            if a and a.manager == "manual":
                how = "manual — tải & cài tay, sẽ mở trang tải"
            if it.app.get("popular"):
                how += ", không mở nguồn"
            rows.append({"id": it.id, "name": it.app["name"], "desc": it.app["desc"],
                         "kind": core.kind_of(it.app), "how": how, "default": it.id in core_ids,
                         "ok": a is not None, "group": origin.get(it.id, "Khác"),
                         "tip": core.tooltip_for(it.app, a, env.os),
                         "present": (lambda sc, i=it: core.is_present(i, sc, env))})
        return rows, selfhost

    # ------------------------------------------------------------ vẽ danh sách
    def section(parent, key, title, level, on_all=None):
        """Khung gom gọn được: nút [-]/[+] ở đầu."""
        head = ttk.Frame(parent)
        head.pack(fill="x", pady=(6 if level == 0 else 2, 1), padx=level * 14)
        box = ttk.Frame(parent)
        is_closed = collapsed.get(key, False)
        btn = ttk.Button(head, width=3, text="[+]" if is_closed else "[-]")

        def flip():
            collapsed[key] = not collapsed.get(key, False)
            if collapsed[key]:
                box.pack_forget()
                btn.configure(text="[+]")
            else:
                box.pack(fill="x", after=head)
                btn.configure(text="[-]")
        btn.configure(command=flip)
        btn.pack(side="left")
        ttk.Label(head, text=title, font=("TkDefaultFont", 10 if level else 11, "bold")).pack(side="left", padx=6)
        if on_all:
            ttk.Button(head, text="Chọn hết", width=9, command=lambda: on_all(True)).pack(side="left", padx=2)
            ttk.Button(head, text="Bỏ hết", width=8, command=lambda: on_all(False)).pack(side="left")
        if not is_closed:
            box.pack(fill="x", after=head)
        return box

    def link_row(parent, text, url):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=30)
        ttk.Button(row, text="Mở", width=5, command=lambda: webbrowser.open(url)).pack(side="left")
        lbl = ttk.Label(row, text=text)
        lbl.pack(side="left", padx=6)
        Tip(lbl, url)

    def draw_discover(selfhost):
        dbox = section(inner, "discover", "GỢI Ý TỰ TRIỂN KHAI (self-host) & KHÁM PHÁ GITHUB", 0)
        h = ttk.Label(dbox, text="Self-host = phần mềm máy chủ tự dựng (Docker/VPS), không cài tự động.", foreground="#555")
        h.pack(anchor="w", padx=30)
        if selfhost:
            stars = state["stars"]
            for sid in selfhost:
                a = apps[sid]
                st = stars.get(a.get("repo"))
                star_txt = f"★ {st:,}  " if st else ""
                link_row(dbox, f"{star_txt}{a['name']} — {a['desc']}", a["url"])
            repos = [apps[s]["repo"] for s in selfhost if apps[s].get("repo")]
            ttk.Button(dbox, text="Lấy số sao các gợi ý trên",
                       command=lambda: fetch_suggestion_stars(repos)).pack(anchor="w", padx=30, pady=3)
        bar = ttk.Frame(dbox)
        bar.pack(fill="x", padx=30, pady=(8, 2))
        ttk.Label(bar, text="Chủ đề:").pack(side="left")
        cb = ttk.Combobox(bar, textvariable=topic_var, width=36,
                          values=[lbl for lbl, _ in core.DISCOVER_PRESETS.values()])
        cb.pack(side="left", padx=4)
        Tip(cb, "Chọn một chủ đề có sẵn, hoặc gõ truy vấn GitHub tự do, ví dụ:\n"
                "  invoice language:php\n  topic:crm topic:self-hosted")
        ttk.Label(bar, text="Top:").pack(side="left", padx=(8, 0))
        ttk.Spinbox(bar, from_=5, to=100, increment=5, textvariable=top_var, width=5).pack(side="left", padx=4)
        ttk.Button(bar, text="Quét GitHub", command=run_discover).pack(side="left", padx=6)
        ttk.Button(bar, text="Lưu kết quả", command=save_disc).pack(side="left")
        if state["disc_msg"]:
            ttk.Label(dbox, text=state["disc_msg"], foreground="#a33").pack(anchor="w", padx=30)
        for i, r in enumerate(state["disc"], 1):
            link_row(dbox, f"{i:>2}. ★ {r['stars']:,}  {r['full_name']} — {r['desc'][:90]}  [{r['license']}]", r["url"])

    def draw_legend():
        lbox = section(inner, "legend", "CHÚ GIẢI (winget, apt, manual, ✓ … nghĩa là gì?)", 0)
        for k, v in core.LEGEND.items():
            row = ttk.Frame(lbox)
            row.pack(fill="x", padx=30, pady=1)
            ttk.Label(row, text=k, width=16, font=("TkDefaultFont", 9, "bold")).pack(side="left", anchor="n")
            ttk.Label(row, text=v, wraplength=620, justify="left").pack(side="left")

    def refresh(reset: bool):
        if reset:
            avars.clear()
        for w in inner.winfo_children():
            w.destroy()
        draw_legend()
        rows, selfhost = build_rows()
        if mode.get() != "pack" and state["scan"] is None and not state["scanning"] and rows:
            rescan()
        have = present_ids(rows) if mode.get() != "pack" else set()
        for r in rows:
            r["have"] = r["id"] in have and not force.get()

        def setter(group):
            def f(val):
                for r in group:
                    if r["ok"] and not r["have"]:
                        avars[r["id"]].set(val)
            return f

        for kind in ("runtime", "app"):
            kg = [r for r in rows if r["kind"] == kind]
            if not kg:
                continue
            n_have = sum(1 for r in kg if r["have"])
            title = f"{core.KIND_LABEL[kind]} — {len(kg)} mục" + (f", {n_have} đã có" if n_have else "")
            kbox = section(inner, kind, title, 0, setter(kg))
            groups: dict[str, list] = {}
            for r in kg:
                groups.setdefault(r["group"], []).append(r)
            for gname, grows in groups.items():
                gbox = section(kbox, f"{kind}/{gname}", f"{gname} ({len(grows)})", 1, setter(grows))
                for r in grows:
                    var = avars.get(r["id"]) or tk.BooleanVar(value=r["default"] and r["ok"] and not r["have"])
                    avars[r["id"]] = var
                    label = r["name"] + (f" — {r['desc']}" if r["desc"] else "") + f"   [{r['how']}]"
                    if r["have"]:
                        label = "✓ đã cài  " + label
                    cb = ttk.Checkbutton(gbox, text=label, variable=var)
                    if r["have"] or not r["ok"]:
                        var.set(False)
                        cb.state(["disabled"])
                    cb.pack(anchor="w", padx=44)
                    Tip(cb, r["tip"])
        if mode.get() != "offline":
            draw_discover(selfhost)
        entry.state(["!disabled"] if mode.get() != "online" else ["disabled"])
        for w in left.winfo_children():
            if isinstance(w, ttk.Checkbutton):
                w.state(["disabled"] if mode.get() == "offline" else ["!disabled"])

    # ------------------------------------------------------------ dưới: chạy + log
    bottom = ttk.Frame(root)
    bottom.pack(fill="x", padx=8)
    c1 = ttk.Checkbutton(bottom, text="Chạy thử (dry-run)", variable=dry)
    c1.pack(side="left")
    Tip(c1, core.LEGEND["dry-run"])
    c2 = ttk.Checkbutton(bottom, text="Cài lại cả mục đã có", variable=force, command=lambda: refresh(False))
    c2.pack(side="left", padx=14)
    Tip(c2, "Bỏ qua bước kiểm tra trùng: cài cả những mục đã đánh dấu '✓ đã cài'.")
    log = tk.Text(root, height=9, state="disabled")
    log.pack(side="bottom", fill="x", padx=8, pady=6)

    def pump():
        try:
            while True:
                msg = q.get_nowait()
                if msg == SCAN_DONE:
                    q.put("Quét xong.")
                    refresh(False)
                    continue
                if isinstance(msg, tuple):
                    kind, data, err = msg
                    if kind == "disc":
                        state["disc"] = data
                        state["disc_msg"] = f"Lỗi: {err}" if err else f"Tìm thấy {len(data)} repo (sắp theo số sao)."
                    else:
                        state["stars"].update({k: v for k, v in data.items() if v})
                        state["disc_msg"] = ""
                    refresh(False)
                    continue
                log.configure(state="normal")
                log.insert("end", msg + "\n")
                log.see("end")
                log.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(150, pump)

    def go():
        m = mode.get()
        picked = [i for i, v in avars.items() if v.get()]
        if not picked:
            q.put("Chưa chọn mục nào (hoặc tất cả đã có sẵn).")
            return
        if m != "online" and env.os != "windows" and not dry.get():
            q.put("Chế độ offline chỉ hỗ trợ Windows (winget download). Bật 'Chạy thử' để xem trước.")
            return
        btn.state(["disabled"])

        def work():
            try:
                if m == "online":
                    res = core.run_items(core.make_items(apps, picked, env), env, dry_run=dry.get(),
                                         emit=q.put, present=set())  # đã lọc trùng ở bước chọn
                elif m == "pack":
                    res = core.pack_items(core.make_items(apps, picked, env), folder.get(),
                                          emit=q.put, dry_run=dry.get())
                    if not dry.get():
                        q.put(f"\nGói offline: {folder.get()} — mang cả thư mục sang máy đích, chạy install-offline.bat")
                else:
                    res = core.run_pack(folder.get(), only=picked, dry_run=dry.get(), emit=q.put,
                                        skip_installed=not force.get())
                core.summarize(res, emit=q.put)
                if m == "online" and not dry.get():   # mục manual: mở trang tải để người dùng tải tay
                    for rid, st, url in res:
                        if st == "manual" and url.startswith("http"):
                            q.put(f"Mở trang tải: {url}")
                            webbrowser.open(url)
            except Exception as e:
                q.put(f"LỖI: {e}")
            finally:
                btn.state(["!disabled"])
        threading.Thread(target=work, daemon=True).start()

    btn = ttk.Button(bottom, text="Bắt đầu", command=go)
    btn.pack(side="right")
    refresh(True)
    pump()
    root.mainloop()
