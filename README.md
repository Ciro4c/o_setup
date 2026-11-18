# osetup — Thiết lập phần mềm ban đầu theo nhóm người dùng

Chọn nhóm (học sinh, văn phòng, kỹ sư, thiết kế, kinh doanh, kế toán, marketing, giải trí, media, lập trình) → công cụ tự cài bộ phần mềm **mã nguồn mở / repo GitHub nhiều sao** phù hợp bằng trình quản lý gói của hệ điều hành.

- Python 3.9+, **không cần cài thêm thư viện**.
- Windows → `winget` · macOS → `brew` · Linux → `apt` / `flatpak`.
- Có CLI, menu tương tác và GUI (tkinter).

## Tạo file osetup.exe (Windows)

**Cách 1 — trên máy Windows:** nhấp đúp `build.bat`. File tự cài Python (nếu thiếu), kéo `pyinstaller`, chạy test rồi build ra `dist\osetup.exe` (một file duy nhất, đã gói sẵn danh mục, tự xin quyền Admin). Nhấp đúp exe để mở GUI.

**Cách 2 — không cần Windows:** đẩy thư mục này lên GitHub, vào tab Actions → `build-exe` → *Run workflow*. Lấy `osetup.exe` ở mục Artifacts (hoặc gắn tag `v0.2.0` để tự tạo Release).

Muốn thêm phần mềm riêng mà không build lại: đặt `custom.json` cạnh `osetup.exe`.


## Hai chế độ cài đặt

| | Chế độ 1 — Online | Chế độ 2 — Offline |
|---|---|---|
| Cách dùng | Chạy → chọn nhóm / môi trường / phần mềm → tải & cài ngay | **Bước 1 (có mạng):** chạy → chọn → chỉ tải về thư mục gói. **Bước 2 (không cần mạng):** mang thư mục sang máy đích → chạy `install-offline.bat` |
| GUI | chọn *"1. Online"* | *"2. Tạo gói offline"* rồi *"3. Cài từ gói offline"* |
| CLI | `osetup install office student -y` | `osetup pack office student -d D:\pack` rồi `osetup offline-install -d D:\pack -y` |
| Hệ điều hành | Windows / macOS / Linux | **Windows** (dựa trên `winget download`) |

Thư mục gói gồm: mỗi app một thư mục installer, `pack.json` (danh mục + tham số cài ngầm), bản sao `osetup.exe`, `install-offline.bat`, và `CAI-THU-CONG.txt` (các mục không tải tự động được như OpenKey). Khi cài offline, **môi trường luôn được cài trước, phần mềm sau**; app đã có trên máy sẽ được bỏ qua. Installer dạng zip/portable không tự cài được và sẽ được báo để cài tay.

## Chọn tất cả nhóm, gom gọn, kiểm tra trùng

- **Tất cả nhóm:** GUI có ô *★ TẤT CẢ các nhóm*; CLI dùng `osetup install all` (hoặc `--everything`); menu văn bản chọn `0`.
- **Gom gọn:** mọi khu trong GUI (Môi trường, Phần mềm, từng nhóm con, self-host) có nút **[-]/[+]** để thu gọn / mở ra; mỗi khu có *Chọn hết / Bỏ hết*.
- **Kiểm tra trước, không cài trùng:** trước khi cài, công cụ quét máy **một lần** (winget list / dpkg / flatpak / brew) và kiểm thêm lệnh trong PATH (git, node, ffmpeg…). Mục đã có được đánh dấu **✓ đã cài**, tự bỏ chọn và bỏ qua khi cài. Dùng `osetup check office` để chỉ xem còn thiếu gì; thêm `--force` (CLI) hoặc tích *Cài lại cả mục đã có* (GUI) nếu muốn cài lại. Chế độ cài từ gói offline cũng quét máy đích và bỏ qua mục đã có.

## Chú giải và khám phá GitHub

- **Chú giải:** GUI có khu *CHÚ GIẢI* (mở bằng `[+]`) giải thích `winget`, `brew`, `cask`, `apt`, `flatpak`, `manual`, `không mở nguồn`, `✓ đã cài`, môi trường / phần mềm, self-host, dry-run. Rê chuột lên một mục để xem tooltip (cách cài, ID gói, giấy phép, repo). CLI: `osetup legend`; các lệnh `install` / `check` cũng in chú giải cho những thẻ có trong kế hoạch.
- **Quét GitHub (top N repo nhiều sao):** trong khu *GỢI Ý TỰ TRIỂN KHAI* chọn chủ đề (Self-hosted, CRM, ERP, Kế toán, Wiki, BI, AI cục bộ… hoặc gõ truy vấn GitHub tự do như `invoice language:php`), chọn *Top* (5–100) rồi bấm **Quét GitHub**. Mỗi kết quả có nút *Mở* để xem repo; *Lưu kết quả* ghi vào `~/.osetup/custom.json` (nhóm "Của tôi"). Nút *Lấy số sao các gợi ý trên* cập nhật ★ cho danh sách gợi ý có sẵn.
- CLI: `osetup discover crm --top 20`, `osetup discover "invoice" --lang php --save`, `osetup discover --list-presets`.
- Dùng API tìm kiếm của GitHub: chưa đăng nhập chỉ được ~10 lượt/phút — đặt biến `GITHUB_TOKEN` để nới giới hạn.

## Môi trường và phần mềm

Danh mục chia hai loại (`"kind"` trong catalog): **MÔI TRƯỜNG** (`runtime`) là thứ phần mềm khác cần để chạy hoặc để lập trình: VC++ Redistributable, .NET, Java, WebView2, DirectX, PowerShell 7, Python, Node.js, Git, Go, Rust, CMake, R, SDK… và **PHẦN MỀM** (`app`) là ứng dụng người dùng. Cả CLI lẫn GUI hiển thị hai khu riêng, có nút *Chọn hết / Bỏ hết* cho từng khu; dùng `--env-only` hoặc `--apps-only` để chỉ cài một loại.

## Chạy nhanh

**Windows** (PowerShell): `.\install.ps1` (tự cài Python nếu thiếu) hoặc nhấp đúp `run.bat` để mở GUI.
**Linux / macOS**: `./install.sh`

## Lệnh

```bash
python -m osetup                       # menu tương tác
python -m osetup list                  # các nhóm
python -m osetup show accounting       # chi tiết một nhóm (gồm phần tuỳ chọn)
python -m osetup install student office --dry-run   # xem trước, chưa cài gì
python -m osetup install design marketing -y        # cài thật, không hỏi
python -m osetup install dev --all     # kèm cả phần mềm optional
python -m osetup install media --skip blender,ytdlp
python -m osetup install dev --env-only          # chỉ môi trường lập trình
python -m osetup install design --apps-only      # chỉ phần mềm
python -m osetup pack office student -d D:\pack   # chế độ offline, bước 1
python -m osetup offline-install -d D:\pack -y   # chế độ offline, bước 2
python -m osetup export sales -o sales.ps1          # xuất script để xem/mang sang máy khác
python -m osetup --target windows export office     # xuất cho OS khác với máy đang chạy
python -m osetup stars design          # xếp hạng theo sao GitHub (cần mạng; đặt GITHUB_TOKEN để tránh giới hạn)
python -m osetup verify                # kiểm tra ID gói còn tồn tại trong kho không
python -m osetup gui
```

Có thể chọn nhiều nhóm cùng lúc; app trùng chỉ cài một lần. Hai nhóm nền tảng luôn kèm theo: `base` (trình duyệt, 7-Zip, VLC, KeePassXC, đọc PDF, bộ gõ tiếng Việt, Notepad++, Git…, tắt bằng `--no-base`) và `runtimes` (VC++ 2010-2022 x86/x64, .NET Desktop 6/8/9, Java 17/21, WebView2, DirectX, PowerShell 7; Linux: build-essential, codec, font…, tắt bằng `--no-runtimes`). `--popular` thêm phần mềm miễn phí nhưng không mở nguồn (Chrome, Zalo, Zoom, Steam…); `--everything` chọn mọi nhóm. Gói đã cài sẽ được bỏ qua; một gói lỗi không làm dừng cả quá trình. Log lưu ở `~/.osetup/`.

## Các nhóm

| id | Nhóm | Phần mềm chính |
|---|---|---|
| student | Học sinh / Sinh viên | LibreOffice, Anki, Zotero, Calibre, Xournal++, Joplin |
| office | Văn phòng | LibreOffice, Thunderbird, Jitsi, NAPS2, PDF Arranger, ShareX, Telegram |
| engineer | Kỹ sư | FreeCAD, LibreCAD, KiCad, QGIS, Octave, Arduino IDE, Python |
| dev | Lập trình | Git, VSCodium, Python, Node.js, Neovim, Podman Desktop, DBeaver, Bruno |
| design | Thiết kế | GIMP, Inkscape, Krita, Scribus, darktable, Blender |
| sales | Kinh doanh | LibreOffice, Thunderbird, Jitsi, Nextcloud, Bitwarden + gợi ý CRM |
| accounting | Kế toán | LibreOffice, GnuCash, NAPS2, Tesseract + gợi ý ERPNext/Odoo/Akaunting |
| gov-tax | Nhà nước – Thuế | HTKK, iTaxViewer, cổng Thuế điện tử/DVC thuế, tra cứu MST, Java 8 |
| gov-insurance | Nhà nước – BHXH | Cổng BHXH (GDĐT, DVC, TNHS) + I-VAN (eBHXH, VNPT-BHXH, VIN-BHXH) |
| gov-service | Nhà nước – Dịch vụ công | Cổng DVC quốc gia, VNeID, hải quan/ECUS5 |
| gov-esign | Nhà nước – Chữ ký số | VGCA, VNPT-CA, Viettel-CA, FPT-CA, BkavCA (chọn đúng CA của bạn) |

> Nhóm `gov-*` chủ yếu là mục **manual**: osetup mở trang tải chính thức của cơ quan/nhà cung cấp, bạn tự tải và cài. Hãy kiểm lại URL/phiên bản trên trang chính thức; driver token phụ thuộc nhà cung cấp chữ ký số của bạn.
| marketing | Marketing | GIMP, Inkscape, OBS, Shotcut, Kdenlive, Audacity, HandBrake |
| entertainment | Giải trí | VLC, Kodi, Jellyfin Player, RetroArch, SuperTuxKart, Heroic |
| utilities | Tiện ích IT | Sysinternals, WinDirStat, Rufus, Ventoy, CrystalDisk, RustDesk, WinSCP |
| science | Khoa học dữ liệu | Python, R, RStudio, LaTeX, Zotero, ParaView, QGIS |
| ai | AI cục bộ | Ollama (+ gợi ý Open WebUI) |
| media | Media | OBS, Kdenlive, Shotcut, Audacity, FFmpeg, MKVToolNix, LMMS |

Các ứng dụng dạng **server** (Odoo, ERPNext, Twenty CRM, Matomo, Penpot, Jellyfin, Nextcloud…) không cài tự động mà được liệt kê dưới mục "self-host" kèm link repo.

## Tuỳ chỉnh

Tạo `~/.osetup/custom.json` (tự nạp) hoặc truyền `--profile-file file.json` để thêm app / nhóm / ghi đè:

```json
{
  "apps": {
    "myapp": {"name": "MyApp", "desc": "Mô tả", "repo": "owner/repo",
              "winget": "Publisher.MyApp", "brew": "myapp", "apt": "myapp", "flatpak": "org.x.MyApp"}
  },
  "profiles": {
    "ke-toan-vn": {"name": "Kế toán VN", "desc": "…", "core": ["libreoffice", "gnucash", "myapp"]}
  }
}
```

Khoá gói: `winget`, `brew` (formula), `cask` (macOS app), `apt`, `flatpak`; `manual: {"windows": "<url>"}` cho phần mềm chỉ tải tay được.

## Lưu ý

- **Chế độ offline chưa thử trên Windows thật.** Luồng tải → ghi `pack.json` → cài ngầm đã được kiểm bằng winget giả. Tham số cài ngầm đọc từ manifest của winget; installer nào không có sẽ dùng mặc định theo loại (inno `/VERYSILENT`, nullsoft `/S`, burn/wix `/quiet`, msi `/qn`) nên một vài app có thể cần chỉnh.
- **Nhận diện "đã cài" dựa vào ID winget:** app cài ngoài winget (tải .exe tay) có thể không nhận ra nếu không có lệnh trong PATH; khi đó winget thường tự báo "đã có" và bỏ qua. Cột ID của `winget list` bị cắt bớt trên cửa sổ hẹp có thể gây nhận sót.
- **Chưa kiểm tra ID gói trên máy thật.** Tên gói winget/brew/flatpak đôi khi đổi. Chạy `python -m osetup verify` trên máy đích để phát hiện ID sai, rồi sửa trong `osetup/data/catalog.json` hoặc `custom.json`.
- Phần mềm kế toán Việt Nam (MISA, Fast, Bravo…) và bộ gõ UniKey/EVKey không mã nguồn mở nên không có trong danh mục; thêm bằng `custom.json` nếu cần.
- Một số mục chỉ có trên một hệ điều hành (ShareX, Notepad++, SumatraPDF… cho Windows) — hệ khác sẽ báo "không hỗ trợ" và bỏ qua.
- Trên Linux, bản `apt` có thể cũ hơn; dùng `--prefer flatpak` để lấy bản mới.

Chạy test: `python -m unittest discover -s tests`


## Trang web (GitHub Pages)

`docs/index.html` là một trang chạy được: chọn hệ điều hành + nhóm → tick/bỏ tick → tải script cài đặt
(`.bat` cho Windows dùng winget, `.sh` cho macOS/Linux; có chế độ tải offline cho Windows).
Trang được sinh từ dữ liệu trong `osetup/data/`; sau khi sửa catalog/profiles hãy chạy lại:

```
python tools/build_site.py
```

## Trợ lý tự động & cài 1 dòng lệnh

- **Bot cập nhật** (`.github/workflows/refresh.yml`): mỗi ngày tự cào top 20 GitHub theo từng chủ đề + số sao của mọi repo trong danh mục, dựng lại `docs/index.html` rồi commit. Chạy ngay: tab **Actions → refresh-data → Run workflow**.
- **Cài 1 dòng lệnh** (hiện sẵn trên trang web, đổi theo nhóm/tick bạn chọn):
  - Windows (PowerShell, Run as administrator): `$env:OSETUP_ARGS='install student -y'; irm https://<user>.github.io/<repo>/install.ps1 | iex`
  - Linux/macOS: `curl -fsSL https://<user>.github.io/<repo>/install.sh | OSETUP_ARGS='install student -y' bash`
  - Lệnh tự dò máy, mục nào đã cài thì bỏ qua. Thêm `-n` để chạy thử.
- **Đẩy lên GitHub nhanh**: bấm đúp `sync.bat` (add + commit + push).
- Sửa `tools/bootstrap/install.*` nếu đổi tên repo, rồi chạy `python tools/build_site.py`.
