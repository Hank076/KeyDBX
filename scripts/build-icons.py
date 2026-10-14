#!/usr/bin/env python3
"""從 `web/icons/` 的原始 SVG 產生網站的 favicon 與 web app manifest 圖示到 `web/site/`。

在 App repo 根目錄執行：python3 web/scripts/build-icons.py

需要 Google Chrome（/Applications/Google Chrome.app）：PNG 以 headless Chrome 截圖產生，
ICO 以標準函式庫把 PNG 包進 ICO 容器。同樣的輸入與 Chrome 版本產生逐位元組相同的檔案。

產出：
- favicon.svg：favicon-16.svg 的原樣複本。
- favicon.ico：16（favicon-16.svg）、32、48（favicon-64.svg）三張 PNG。
- favicon-96x96.png：favicon-64.svg。
- apple-touch-icon.png（180）、web-app-manifest-192x192.png、web-app-manifest-512x512.png：icon-full.svg。

所有產出先在暫存目錄產生並驗證，全部通過後才寫入 `site/`。任何一步失敗時以結束碼 1 結束，
`site/` 不變，訊息列出檔案、期望值與實得值。
"""

import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
ICONS = WEB / "icons"
SITE = WEB / "site"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR_RGB = 2
COLOR_RGBA = 6
COLOR_NAMES = {0: "灰階", 2: "RGB", 3: "索引色", 4: "灰階＋alpha", 6: "RGBA"}
BYTES_PER_PIXEL = {COLOR_RGB: 3, COLOR_RGBA: 4}

# 圓角的 favicon 四角透明，PNG 必須是 RGBA。滿版的圖示完全不透明，Chrome 以 RGB 編碼：
# 滿版圖示若變成 RGBA，代表背景沒有畫滿。
ROUNDED = COLOR_RGBA
FULL_BLEED = COLOR_RGB

# (輸出檔名, 原始 SVG, 邊長, 期望的 PNG color type)
PNG_OUTPUTS = [
    ("favicon-96x96.png", "favicon-64.svg", 96, ROUNDED),
    ("apple-touch-icon.png", "icon-full.svg", 180, FULL_BLEED),
    ("web-app-manifest-192x192.png", "icon-full.svg", 192, FULL_BLEED),
    ("web-app-manifest-512x512.png", "icon-full.svg", 512, FULL_BLEED),
]
# favicon.ico 的內容，依尺寸由小到大排列。
ICO_MEMBERS = [
    ("favicon-16.svg", 16, ROUNDED),
    ("favicon-64.svg", 32, ROUNDED),
    ("favicon-64.svg", 48, ROUNDED),
]


def fail(message):
    print(f"錯誤：{message}", file=sys.stderr)
    sys.exit(1)


def read_svg(name):
    """讀取原始 SVG 的 bytes，確認它以 `<svg ` 開頭。"""
    path = ICONS / name
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(f"無法讀取 {path}：{exc}")
    if not data.startswith(b"<svg "):
        fail(f"{path} 應以 '<svg ' 開頭，實得 {data[:20]!r}")
    return data


def page_html(svg, size):
    """截圖用的頁面。svg 以 display:block 排版：inline 的 svg 會對齊文字基線，在標準模式下往下偏移。"""
    sized = svg.strip().replace("<svg ", f'<svg width="{size}" height="{size}" style="display:block" ', 1)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f"<body style=\"margin:0;background:transparent\">{sized}</body></html>"
    )


def png_header(data, label):
    """回傳 PNG 的 (寬, 高, bit depth, color type, interlace)。格式不符時結束。"""
    if data[:8] != PNG_SIGNATURE:
        fail(f"{label}：不是 PNG，前 8 bytes 為 {data[:8].hex()}")
    length, chunk = struct.unpack(">I4s", data[8:16])
    if chunk != b"IHDR" or length != 13:
        fail(f"{label}：第一個 chunk 應為長度 13 的 IHDR，實得 {chunk!r}（長度 {length}）")
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", data[16:29])
    return width, height, depth, color, interlace


def png_pixel(data, label, x, y):
    """解碼 8-bit、非交錯的 RGB／RGBA PNG，回傳 (x, y) 的 RGBA。"""
    width, height, depth, color, interlace = png_header(data, label)
    if depth != 8 or color not in BYTES_PER_PIXEL or interlace != 0:
        fail(f"{label}：只能解碼 8-bit、非交錯的 RGB／RGBA，實得 bit depth {depth}、color type {color}、interlace {interlace}")
    compressed = bytearray()
    pos = 8
    while pos + 8 <= len(data):
        length, chunk = struct.unpack(">I4s", data[pos:pos + 8])
        if chunk == b"IDAT":
            compressed += data[pos + 8:pos + 8 + length]
        if chunk == b"IEND":
            break
        pos += 12 + length
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        fail(f"{label}：IDAT 解壓縮失敗：{exc}")
    bpp = BYTES_PER_PIXEL[color]
    stride = width * bpp
    if len(raw) != height * (stride + 1):
        fail(f"{label}：解壓縮後應為 {height * (stride + 1)} bytes，實得 {len(raw)} bytes")
    previous = bytearray(stride)
    for row in range(y + 1):
        start = row * (stride + 1)
        kind = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up = previous[i]
            up_left = previous[i - bpp] if i >= bpp else 0
            if kind == 0:
                predictor = 0
            elif kind == 1:
                predictor = left
            elif kind == 2:
                predictor = up
            elif kind == 3:
                predictor = (left + up) // 2
            elif kind == 4:
                estimate = left + up - up_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - up_left))
                predictor = left if distances[0] <= distances[1] and distances[0] <= distances[2] else (
                    up if distances[1] <= distances[2] else up_left
                )
            else:
                fail(f"{label}：第 {row} 列的 filter type 應為 0 到 4，實得 {kind}")
            line[i] = (line[i] + predictor) & 0xFF
        previous = line
    pixel = tuple(previous[x * bpp:(x + 1) * bpp])
    return pixel if bpp == 4 else pixel + (255,)


def render(svg_name, size, color_type, tmp):
    """以 headless Chrome 把 SVG 截成 size×size 的 PNG，驗證後回傳 PNG bytes。"""
    label = f"{svg_name} → {size}×{size}"
    work = tmp / f"{Path(svg_name).stem}-{size}"
    work.mkdir()
    page = work / "page.html"
    page.write_text(page_html(read_svg(svg_name).decode("utf-8"), size), encoding="utf-8")
    out = work / "shot.png"
    command = [
        str(CHROME),
        "--headless",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--force-color-profile=srgb",
        "--default-background-color=00000000",
        f"--window-size={size},{size}",
        # 獨立的設定檔目錄與模擬的鑰匙圈：不與使用者開著的 Chrome 共用設定檔，也不跳出鑰匙圈存取提示。
        f"--user-data-dir={work / 'profile'}",
        "--use-mock-keychain",
        "--no-first-run",
        "--no-default-browser-check",
        f"--screenshot={out}",
        page.as_uri(),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        fail(f"{label}：Chrome 截圖超過 120 秒沒有結束")
    if result.returncode != 0 or not out.is_file():
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        fail(f"{label}：Chrome 截圖失敗，結束碼 {result.returncode}，輸出檔{'存在' if out.is_file() else '不存在'}\n{tail}")
    data = out.read_bytes()
    width, height, depth, color, interlace = png_header(data, label)
    if (width, height, depth, color, interlace) != (size, size, 8, color_type, 0):
        fail(
            f"{label}：PNG 應為 {size}×{size}、bit depth 8、{COLOR_NAMES[color_type]}（color type {color_type}）、非交錯，"
            f"實得 {width}×{height}、bit depth {depth}、{COLOR_NAMES.get(color, '未知')}（color type {color}）、interlace {interlace}"
        )
    # 圖案中心是鑰匙孔，必須不透明：截到空白頁時中心是透明的。
    center = png_pixel(data, label, size // 2, size // 2)
    if center[3] != 255:
        fail(f"{label}：中心像素 ({size // 2}, {size // 2}) 應不透明（alpha 255），實得 RGBA {center}")
    return data


def build_ico(images):
    """把 [(邊長, PNG bytes)] 包成 ICO。目錄項的寬高以 1 byte 表示，0 代表 256。"""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    payload = b""
    for size, data in images:
        if not 1 <= size <= 256:
            fail(f"ICO 不支援 {size}×{size}，邊長應在 1 到 256 之間")
        dimension = size % 256
        # 寬、高、調色盤色數、保留、color planes、bits per pixel、資料長度、資料位移
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    return header + entries + payload


def install(outputs):
    """把 {檔名: bytes} 寫入 site/。先全部寫成同目錄的暫存檔，再逐一 os.replace 換上：
    寫暫存檔失敗時刪除已寫的暫存檔，site/ 的既有檔案不變。"""
    staged = []
    try:
        for name, data in outputs.items():
            handle, temp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=SITE)
            staged.append((Path(temp), SITE / name))
            with os.fdopen(handle, "wb") as file:
                file.write(data)
            os.chmod(temp, 0o644)
    except OSError as exc:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        fail(f"無法寫入 {SITE}：{exc}")
    for temp, target in staged:
        os.replace(temp, target)


def main():
    if not CHROME.is_file():
        fail(f"找不到 Google Chrome，需要 {CHROME}。請安裝 Google Chrome 後再執行。")
    if not SITE.is_dir():
        fail(f"找不到網站目錄 {SITE}")

    outputs = {"favicon.svg": read_svg("favicon-16.svg")}
    # 暫存的頁面、截圖與 Chrome 設定檔在離開 with 時刪除。
    with tempfile.TemporaryDirectory(prefix="keydbx-icons-") as tmp:
        tmp = Path(tmp)
        members = [(size, render(svg, size, color, tmp)) for svg, size, color in ICO_MEMBERS]
        outputs["favicon.ico"] = build_ico(members)
        for name, svg, size, color in PNG_OUTPUTS:
            outputs[name] = render(svg, size, color, tmp)

    install(outputs)
    print("產生圖示：")
    for name, data in outputs.items():
        print(f"  web/site/{name}  {len(data)} bytes")


if __name__ == "__main__":
    main()
