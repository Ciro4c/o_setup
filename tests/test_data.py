import re
import unittest

from osetup import core


class DataIntegrity(unittest.TestCase):
    def setUp(self):
        self.apps, self.profiles = core.load_data()

    def test_profile_refs_exist(self):
        for pid, p in self.profiles.items():
            for key in ("core", "optional", "popular", "selfhost"):
                for aid in p.get(key, []):
                    self.assertIn(aid, self.apps, f"{pid}.{key}: {aid}")

    def test_selfhost_only_in_selfhost(self):
        for pid, p in self.profiles.items():
            for aid in p.get("core", []) + p.get("optional", []):
                self.assertFalse(self.apps[aid].get("popular"), f"{pid}: {aid} là popular, đặt vào mục popular")
                self.assertNotEqual(self.apps[aid].get("kind"), "selfhost", f"{pid}: {aid}")
            for aid in p.get("selfhost", []):
                self.assertEqual(self.apps[aid].get("kind"), "selfhost", f"{pid}: {aid}")

    def test_every_app_installable_somewhere(self):
        keys = {"winget", "brew", "cask", "apt", "flatpak", "manual"}
        for aid, a in self.apps.items():
            if a.get("kind") == "selfhost":
                self.assertTrue(a.get("url"), aid)
            else:
                self.assertTrue(keys & a.keys(), aid)
            if a.get("repo"):
                self.assertTrue(re.fullmatch(r"[\w.-]+/[\w.-]+", a["repo"]), f"{aid}: {a['repo']}")
            if a.get("popular"):
                self.assertTrue(a.get("license"), aid)

    def test_all_profiles_resolve_on_each_os(self):
        for target in ("windows", "macos", "linux"):
            env = core.detect_env(target)
            for pid in self.profiles:
                ids, _ = core.build_plan(self.apps, self.profiles, [pid], include_optional=True, include_popular=True)
                items = core.make_items(self.apps, ids, env)
                self.assertGreaterEqual(sum(i.action is not None for i in items), 3, f"{pid}/{target}")

    def test_dedupe_and_flags(self):
        ids, _ = core.build_plan(self.apps, self.profiles, ["office", "sales"])
        self.assertEqual(len(ids), len(set(ids)))
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"], skip=["telegram"], with_base=False)
        self.assertNotIn("telegram", ids)
        self.assertNotIn("firefox", ids)
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"], only=["jitsi"], with_base=False)
        self.assertEqual(ids, ["jitsi"])

    def test_runtimes_always_included_on_windows(self):
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"])
        self.assertIn("vcredist-2015-x64", ids)
        self.assertIn("dotnet8-desktop", ids)
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"], with_runtimes=False)
        self.assertNotIn("vcredist-2015-x64", ids)

    def test_popular_only_when_asked(self):
        ids, _ = core.build_plan(self.apps, self.profiles, ["sales"])
        self.assertNotIn("pop-zalo", ids)
        ids, _ = core.build_plan(self.apps, self.profiles, ["sales"], include_popular=True)
        self.assertIn("pop-zalo", ids)

    def test_quiet_hidden_on_other_os(self):
        env = core.detect_env("linux")
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"])
        names = [i.id for i in core.make_items(self.apps, ids, env)]
        self.assertNotIn("vcredist-2015-x64", names)
        self.assertIn("build-essential", names)

    def test_kind_split_and_order(self):
        env = core.detect_env("windows")
        ids, _ = core.build_plan(self.apps, self.profiles, ["dev"], include_optional=True)
        kinds = [core.kind_of(i.app) for i in core.make_items(self.apps, ids, env)]
        self.assertIn("runtime", kinds)
        self.assertIn("app", kinds)
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "runtime"))  # môi trường trước
        for rid in ("python", "nodejs", "git", "vcredist-2015-x64", "java21-jdk"):
            self.assertEqual(core.kind_of(self.apps[rid]), "runtime", rid)
        self.assertEqual(core.kind_of(self.apps["gimp"]), "app")

    def test_commands(self):
        self.assertEqual(core.command(core.Action("winget", "X.Y"))[:3], ["winget", "install", "--id"])
        self.assertIn("--cask", core.command(core.Action("cask", "vlc")))

    def test_unknown_profile(self):
        with self.assertRaises(KeyError):
            core.build_plan(self.apps, self.profiles, ["nope"])


class Presence(unittest.TestCase):
    def setUp(self):
        self.apps, self.profiles = core.load_data()

    def test_winget_presence_exact_id(self):
        scan = {"winget": "name  id  version\nvlc media  videolan.vlc  3.0\n7-zip  7zip.7zip  24\n"
                          "github desktop  github.githubdesktop  3.4\n"}
        A = core.Action
        self.assertTrue(core.is_present_action(A("winget", "VideoLAN.VLC"), scan))
        self.assertTrue(core.is_present_action(A("winget", "7zip.7zip"), scan))
        self.assertFalse(core.is_present_action(A("winget", "Git.Git"), scan))      # không khớp nhầm GitHub
        self.assertFalse(core.is_present_action(A("winget", "VideoLAN.VLC.Nightly"), scan))

    def test_other_managers(self):
        scan = {"apt": {"vlc"}, "flatpak": {"org.gimp.gimp"}, "brew": set(), "cask": {"firefox"}, "winget": ""}
        self.assertTrue(core.is_present_action(core.Action("apt", "vlc"), scan))
        self.assertTrue(core.is_present_action(core.Action("flatpak", "org.gimp.GIMP"), scan))
        self.assertTrue(core.is_present_action(core.Action("cask", "firefox"), scan))
        self.assertFalse(core.is_present_action(core.Action("manual", "x"), scan))

    def test_skip_present_in_run_items(self):
        env = core.detect_env("windows")
        ids, _ = core.build_plan(self.apps, self.profiles, ["office"], with_runtimes=False)
        items = core.make_items(self.apps, ids, env)
        scan = {"winget": "mozilla.firefox 7zip.7zip"}
        present = core.find_present(items, env, scan)
        self.assertTrue({"firefox", "7zip"} <= present)
        out = []
        res = core.run_items(items, env, dry_run=True, emit=out.append, present=present)
        st = {r[0]: r[1] for r in res}
        self.assertEqual(st["firefox"], "present")
        self.assertEqual(st["libreoffice"], "dry-run")
        self.assertFalse(any("Mozilla.Firefox" in l for l in out))     # không in lệnh cài cho mục có sẵn

    def test_all_profiles(self):
        ids_all, _ = core.build_plan(self.apps, self.profiles, ["all"])
        names = [p for p in self.profiles if p not in core.BASE_PROFILES]
        ids_manual, _ = core.build_plan(self.apps, self.profiles, names)
        self.assertEqual(ids_all, ids_manual)
        self.assertGreater(len(ids_all), 100)


class Discover(unittest.TestCase):
    class _Resp:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return self.data

    def _fake(self, payload, seen):
        import json, urllib.request
        orig = urllib.request.urlopen

        def fake(req, timeout=0):
            seen.append(req.full_url)
            return self._Resp(json.dumps(payload).encode())
        urllib.request.urlopen = fake
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", orig))

    def test_discover_builds_query_and_parses(self):
        seen = []
        self._fake({"items": [
            {"full_name": "a/b", "stargazers_count": 900, "description": "x", "html_url": "https://github.com/a/b",
             "license": {"spdx_id": "MIT"}, "language": "Go", "pushed_at": "2026-01-02T00:00:00Z"},
            {"full_name": "c/d", "stargazers_count": 10, "description": None, "html_url": "https://github.com/c/d",
             "license": None, "language": None, "pushed_at": None}]}, seen)
        rows = core.discover("crm", 20, language="php")
        self.assertIn("topic%3Acrm", seen[0])
        self.assertIn("sort=stars", seen[0])
        self.assertIn("per_page=20", seen[0])
        self.assertIn("language%3Aphp", seen[0])
        self.assertEqual(rows[0]["stars"], 900)
        self.assertEqual(rows[0]["license"], "MIT")
        self.assertEqual(rows[1]["license"], "?")
        self.assertEqual(rows[1]["desc"], "")
        seen.clear()
        core.discover("x", 5000)
        self.assertIn("per_page=100", seen[0])  # giới hạn API

    def test_discover_rate_limit_message(self):
        import urllib.error, urllib.request
        orig = urllib.request.urlopen

        def boom(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 403, "rate", {}, None)
        urllib.request.urlopen = boom
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", orig))
        with self.assertRaises(RuntimeError) as cm:
            core.discover("crm")
        self.assertIn("GITHUB_TOKEN", str(cm.exception))

    def test_save_selfhost_roundtrip(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            old = core.USER_DIR
            core.USER_DIR = Path(t)
            self.addCleanup(lambda: setattr(core, "USER_DIR", old))
            f = core.save_selfhost([{"full_name": "Foo/Bar-App", "stars": 1, "desc": "d", "url": "https://x", "license": "MIT"}])
            core.save_selfhost([{"full_name": "Foo/Bar-App", "stars": 1, "desc": "d", "url": "https://x", "license": "MIT"}])  # lưu lại: không trùng
            apps, profiles = core.load_data()
            self.assertEqual(profiles["my-selfhost"]["selfhost"], ["sh-foo-bar-app"])
            self.assertEqual(apps["sh-foo-bar-app"]["kind"], "selfhost")


class Legend(unittest.TestCase):
    def test_every_manager_in_catalog_has_legend(self):
        apps, _ = core.load_data()
        used = {k for a in apps.values() for k in ("winget", "brew", "cask", "apt", "flatpak", "manual") if k in a}
        for k in used:
            self.assertIn(k, core.LEGEND, k)

    def test_legend_for_and_tooltip(self):
        got = dict(core.legend_for(["winget", "winget", "không mở nguồn, x", "✓ đã cài"]))
        self.assertEqual(set(got), {"winget", "không mở nguồn", "✓ đã cài"})
        apps, _ = core.load_data()
        tip = core.tooltip_for(apps["gimp"], core.Action("winget", "GIMP.GIMP.3"), "windows")
        self.assertIn("winget", tip)
        self.assertIn("GPL-3.0", tip)
        self.assertIn("github.com/GNOME/gimp", tip)


class OfflinePack(unittest.TestCase):
    def _fake_download(self, root, name, typ, silent=None, ext=".exe"):
        d = root / name
        d.mkdir()
        (d / f"setup{ext}").write_bytes(b"x" * 100)
        y = f"PackageIdentifier: X.Y\nInstallers:\n- Architecture: x64\n  InstallerType: {typ}\n"
        if silent:
            y += f"  InstallerSwitches:\n    Silent: {silent}\n"
        (d / "X.Y.yaml").write_text(y, encoding="utf-8")
        return d

    def test_inspect_and_cmd(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            info = core.inspect_download(self._fake_download(t, "a", "inno"))
            self.assertEqual(info["installer"], "setup.exe")
            self.assertEqual(info["type"], "inno")
            self.assertIn("/VERYSILENT", core.installer_cmd(info, "C:/p/setup.exe"))
            info = core.inspect_download(self._fake_download(t, "b", "nullsoft", silent="/S /NCRC"))
            self.assertEqual(core.installer_cmd(info, "s.exe"), ["s.exe", "/S", "/NCRC"])
            info = core.inspect_download(self._fake_download(t, "c", "wix", ext=".msi"))
            self.assertEqual(core.installer_cmd(info, "s.msi")[:2], ["msiexec", "/i"])
            self.assertIsNone(core.installer_cmd({"type": "zip"}, "x.zip"))

    def test_run_pack_dry_and_order(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            items = []
            for i, (k, typ) in enumerate([("app", "inno"), ("runtime", "burn")]):
                self._fake_download(t, f"id{i}", typ)
                items.append({"id": f"id{i}", "name": f"N{i}", "kind": k, "pkg": f"P{i}", "dir": f"id{i}",
                              **core.inspect_download(t / f"id{i}")})
            (t / core.PACK_FILE).write_text(json.dumps({"created": "now", "items": items, "manual": []}))
            out = []
            res = core.run_pack(str(t), dry_run=True, emit=out.append)
            self.assertEqual([r[0] for r in res], ["id1", "id0"])  # runtime trước
            self.assertEqual([r[0] for r in core.run_pack(str(t), only=["id0"], dry_run=True, emit=out.append)], ["id0"])

    def test_pack_dry_run_lists_winget_download(self):
        env = core.detect_env("windows")
        apps, profiles = core.load_data()
        ids, _ = core.build_plan(apps, profiles, ["office"])
        out = []
        res = core.pack_items(core.make_items(apps, ids, env), "/tmp/x", emit=out.append, dry_run=True)
        self.assertTrue(any("winget download" in l for l in out))
        self.assertTrue(any(r[1] == "manual" for r in res))  # OpenKey


class GovProfiles(unittest.TestCase):
    def test_gov_profiles_resolve(self):
        apps, profiles = core.load_data()
        for pid in ("gov-tax", "gov-insurance", "gov-service", "gov-esign"):
            self.assertIn(pid, profiles)
            ids, _ = core.build_plan(apps, profiles, [pid], include_optional=True)
            self.assertTrue(any(i.startswith("gov-") for i in ids), pid)


class AssistantTests(unittest.TestCase):
    def test_origin_rules(self):
        from osetup import assistant as a
        self.assertTrue(a.origin_ok(None))
        self.assertTrue(a.origin_ok("https://ciro4c.github.io"))
        self.assertTrue(a.origin_ok("http://localhost:8123"))
        self.assertFalse(a.origin_ok("https://evil.example"))
        self.assertFalse(a.origin_ok("https://ciro4c.github.io.evil.example"))

    def test_install_rejects_unknown_ids(self):
        from osetup import assistant as a
        with self.assertRaises(ValueError):
            a.start_install(["khong-co-trong-danh-muc"], True)
        with self.assertRaises(ValueError):
            a.start_install(["sh-odoo"] if "sh-odoo" in a.State.apps else ["sh-stirling"], True)


if __name__ == "__main__":
    unittest.main()
