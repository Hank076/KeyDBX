#!/usr/bin/env python3
"""檢查 KeyDBX 網站的靜態檔案（`site/`，Cloudflare Pages 的輸出目錄）。在 App repo 根目錄執行：python3 web/scripts/check-site.py

有任何錯誤時以結束碼 1 結束。每則錯誤包含檔案路徑與原因。
"""

import json
import shutil
import struct
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "site"
SITE_HOST = "keydbx.lab076.dev"

# 允許的站外連結前綴。新增站外連結時，先確認它不會載入資源，再加進這裡。
ALLOWED_EXTERNAL_PREFIXES = (
    "https://github.com/Hank076/KeyDBX/issues",
    "https://github.com/Hank076/KeyDBX/security/advisories/new",
    "https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement",
    "https://www.dropbox.com/privacy",
    "https://www.apple.com/legal/privacy/",
    "https://www.apple.com/tw/legal/privacy/",
    "https://www.cloudflare.com/privacypolicy/",
)

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}

# 一般頁面放行 Cloudflare Web Analytics 的 beacon；/dropbox/oauth/ 的網址帶授權碼，不放行任何 script。
ANALYTICS_SCRIPT_SRC = "https://static.cloudflareinsights.com"
# manifest-src 'self' 讓瀏覽器讀取同網域的 site.webmanifest，default-src 'none' 會擋下它。
EXPECTED_CSP_ANALYTICS = (
    f"default-src 'none'; script-src {ANALYTICS_SCRIPT_SRC}; "
    "connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; img-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'"
)
EXPECTED_CSP_STRICT = (
    "default-src 'none'; style-src 'self'; img-src 'self'; manifest-src 'self'; "
    "base-uri 'none'; form-action 'none'"
)
# 404.html 也用嚴格版：_headers 的路徑比對分大小寫，/Dropbox/OAuth/?code=… 由 404 回應且只套用 /*。
STRICT_CSP_PAGES = {"dropbox/oauth/index.html", "404.html"}
# _headers 另外涵蓋 meta 做不到的 frame-ancestors。
FRAME_ANCESTORS = "; frame-ancestors 'none'"
EXPECTED_AASA = {"webcredentials": {"apps": ["NQ5QFN5794.dev.lab076.KeyDBX"]}}

# 每頁 <head> 的 icon 與 manifest 標籤：(rel, type, sizes, 路徑)。href 為路徑加 ?v=<版本>，
# 所有頁面與 site.webmanifest 的 icon 用同一個版本。icon 由 scripts/build-icons.py 產生。
ICON_LINKS = [
    ("icon", "image/png", "96x96", "/favicon-96x96.png"),
    ("icon", "image/svg+xml", None, "/favicon.svg"),
    ("shortcut icon", None, None, "/favicon.ico"),
    ("apple-touch-icon", None, "180x180", "/apple-touch-icon.png"),
    ("manifest", None, None, "/site.webmanifest"),
]
ICON_RELS = {rel for rel, _, _, _ in ICON_LINKS}
APPLE_TITLE = "KeyDBX"
MANIFEST = "site.webmanifest"
# 固定 start_url：沒有時起始網址等於安裝當下的頁面（可能是帶授權碼的 /dropbox/oauth/?code=…），
# scope 會縮到該頁目錄，id 預設等於 start_url。theme_color 是 header 的深藍，background_color 是網站底色。
EXPECTED_MANIFEST_FIELDS = {
    "id": "/",
    "name": "KeyDBX",
    "short_name": "KeyDBX",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "theme_color": "#0F1828",
    "background_color": "#F2F1EE",
}
# site/favicon.svg 是這個原始檔的原樣複本（scripts/build-icons.py 產生）。
FAVICON_SVG_SOURCE = "icons/favicon-16.svg"
# 只標 maskable 的圖示不會用在一般情境，不支援 maskable 的瀏覽器也不使用它，所以兩種 purpose 都要有。
MANIFEST_PURPOSES = {"any", "maskable"}
MANIFEST_SIZES = {"192x192", "512x512"}
ICO_SIZES = {16, 32, 48}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 中英成對的頁面：(正體中文, 英文)
PAGE_PAIRS = [
    ("index.html", "en/index.html"),
    ("privacy/index.html", "en/privacy/index.html"),
    ("support/index.html", "en/support/index.html"),
]
# 不需要 hreflang 的頁面
NO_HREFLANG = {"404.html", "dropbox/oauth/index.html"}

errors = []


def error(path, message):
    errors.append(f"{path}: {message}")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.problems = []
        self.html_lang = None
        self.metas = []
        self.links = []  # (tag, attr, value)
        self.alternates = []  # (hreflang, href)
        self.stylesheets = []  # <link rel="stylesheet"> 的 href
        self.icons = []  # icon 與 manifest 的 <link>：(rel, type, sizes, href)
        self.counts = {"h2": 0, "li": 0, "details": 0}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.html_lang = attrs.get("lang")
        if tag == "meta":
            self.metas.append(attrs)
        if tag == "link" and attrs.get("rel") == "alternate":
            self.alternates.append((attrs.get("hreflang"), attrs.get("href")))
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.stylesheets.append(attrs.get("href"))
        if tag == "link" and attrs.get("rel") in ICON_RELS:
            self.icons.append((attrs.get("rel"), attrs.get("type"), attrs.get("sizes"), attrs.get("href")))
        for attr in ("href", "src", "action", "formaction", "srcset", "poster", "data"):
            if attr in attrs and attrs[attr] is not None:
                self.links.append((tag, attr, attrs[attr]))
        if tag in self.counts:
            self.counts[tag] += 1
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        # <x /> 形式：只記錄屬性，不入堆疊。
        before = len(self.stack)
        self.handle_starttag(tag, attrs)
        if len(self.stack) > before:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            self.problems.append(f"void 元素 </{tag}> 不應有結束標籤，第 {self.getpos()[0]} 行")
            return
        if not self.stack:
            self.problems.append(f"多出的 </{tag}>，第 {self.getpos()[0]} 行")
            return
        open_tag, pos = self.stack.pop()
        if open_tag != tag:
            self.problems.append(
                f"標籤不成對：第 {pos[0]} 行開啟 <{open_tag}>，第 {self.getpos()[0]} 行卻是 </{tag}>"
            )


def resolve_internal(path):
    """把站內路徑轉成 repo 內的檔案。找不到時回傳 None。"""
    target = ROOT / path.lstrip("/")
    if path.endswith("/"):
        target = target / "index.html"
    if target.is_file():
        return target
    if (target / "index.html").is_file():
        return target / "index.html"
    return None


def check_link(rel, tag, attr, value):
    if value.startswith("#"):
        return
    parts = urlsplit(value)
    if parts.scheme == "http":
        error(rel, f"<{tag} {attr}> 使用 http://：{value}")
        return
    if parts.scheme in ("", None) and not parts.netloc:
        if not value.startswith("/"):
            error(rel, f"<{tag} {attr}> 站內連結要以 / 開頭：{value}")
            return
        if resolve_internal(parts.path) is None:
            error(rel, f"<{tag} {attr}> 指向不存在的檔案：{value}")
        return
    if parts.scheme == "https" and parts.netloc == SITE_HOST:
        if tag == "link" and attr == "href":
            if resolve_internal(parts.path) is None:
                error(rel, f"<link> 指向不存在的頁面：{value}")
            return
        error(rel, f"<{tag} {attr}> 站內連結應使用相對於根目錄的路徑：{value}")
        return
    if tag != "a" or attr != "href":
        error(rel, f"<{tag} {attr}> 載入站外資源：{value}")
        return
    if not value.startswith(ALLOWED_EXTERNAL_PREFIXES):
        error(rel, f"站外連結不在允許清單：{value}")


def check_html(path):
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    if "<script" in lowered:
        error(rel, "含有 <script")
    if "http://" in lowered:
        error(rel, "含有 http://")
    if " style=" in lowered or "<style" in lowered:
        error(rel, "含有 inline style，CSP 的 style-src 'self' 會擋下")

    parser = PageParser()
    parser.feed(text)
    parser.close()
    for problem in parser.problems:
        error(rel, problem)
    for tag, pos in parser.stack:
        error(rel, f"<{tag}>（第 {pos[0]} 行）沒有結束標籤")

    if parser.html_lang not in ("zh-Hant-TW", "en"):
        error(rel, f"<html lang> 應為 zh-Hant-TW 或 en，實得 {parser.html_lang!r}")

    metas = {m.get("name") or m.get("http-equiv"): m.get("content") for m in parser.metas}
    if metas.get("referrer") != "no-referrer":
        error(rel, f"缺少 <meta name=\"referrer\" content=\"no-referrer\">，實得 {metas.get('referrer')!r}")
    expected_csp = EXPECTED_CSP_STRICT if rel in STRICT_CSP_PAGES else EXPECTED_CSP_ANALYTICS
    if metas.get("Content-Security-Policy") != expected_csp:
        error(rel, f"CSP meta 應為 {expected_csp!r}，實得 {metas.get('Content-Security-Policy')!r}")

    for tag, attr, value in parser.links:
        check_link(rel, tag, attr, value)

    if rel not in NO_HREFLANG:
        langs = {lang for lang, _ in parser.alternates}
        if langs != {"zh-Hant-TW", "en"}:
            error(rel, f"hreflang 應為 zh-Hant-TW 與 en，實得 {sorted(l for l in langs if l)}")

    titles = [m.get("content") for m in parser.metas if m.get("name") == "apple-mobile-web-app-title"]
    if titles != [APPLE_TITLE]:
        error(rel, f"應有一個 <meta name=\"apple-mobile-web-app-title\" content=\"{APPLE_TITLE}\">，實得 {titles!r}")

    if rel == "dropbox/oauth/index.html":
        if metas.get("robots") != "noindex":
            error(rel, "缺少 <meta name=\"robots\" content=\"noindex\">")
        for word in ("location", "search", "code="):
            if word in lowered:
                error(rel, f"不得處理網址參數，發現 {word!r}")

    return rel, parser.counts, parser.stylesheets, parser.icons


def check_stylesheets(stylesheets):
    """所有頁面的 stylesheet 網址相同且帶 `?v=`：Cloudflare 讓瀏覽器快取 CSS 4 小時，改 CSS 時要換網址。"""
    hrefs = set()
    for rel in sorted(stylesheets):
        found = stylesheets[rel]
        if len(found) != 1:
            error(rel, f"應有一個 <link rel=\"stylesheet\">，實得 {found!r}")
            continue
        href = found[0] or ""
        version = parse_qs(urlsplit(href).query).get("v", [""])[0]
        if not version:
            error(rel, f"stylesheet 網址應帶 ?v= 版本參數，實得 {href!r}")
        hrefs.add(href)
    if len(hrefs) > 1:
        detail = "；".join(f"{rel} {stylesheets[rel]!r}" for rel in sorted(stylesheets))
        error("site/**/*.html", f"所有頁面的 stylesheet 網址應相同，實得 {detail}")


def url_version(href):
    return parse_qs(urlsplit(href).query).get("v", [""])[0]


def png_size(rel):
    """讀 PNG 的 IHDR，回傳 (寬, 高)。不是 PNG 或讀不到時記錄錯誤並回傳 None。"""
    try:
        data = (ROOT / rel).read_bytes()[:26]
    except OSError as exc:
        error(rel, f"無法讀取：{exc}")
        return None
    return png_size_of(rel, data)


def png_size_of(label, data):
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        error(label, f"不是 PNG（前 16 bytes 為 {data[:16].hex()}）")
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def check_png_matches(label, rel, sizes):
    """`sizes`（例如 "180x180"）與 PNG 實際寬高相符。"""
    actual = png_size(rel)
    if actual is not None and f"{actual[0]}x{actual[1]}" != sizes:
        error(label, f"{rel} 的實際尺寸為 {actual[0]}x{actual[1]}，標示的 sizes 為 {sizes!r}")


def icon_tag(rel, kind):
    return f"<link rel=\"{rel}\"" + (f" type=\"{kind}\"" if kind else "") + ">"


def check_icons(icons):
    """每頁都有 ICON_LINKS 的標籤，href 帶 ?v=、指向存在的檔案，而且所有頁面相同。回傳用到的版本。"""
    hrefs = {}  # (rel, type) → {頁面: href}
    versions = set()
    expected_keys = {(r, t) for r, t, _, _ in ICON_LINKS}
    for rel in sorted(icons):
        found = icons[rel]
        for link in found:
            if (link[0], link[1]) not in expected_keys:
                error(rel, f"多出不在清單內的 {icon_tag(link[0], link[1])}：{link[3]!r}")
        for want_rel, want_type, want_sizes, want_path in ICON_LINKS:
            tag = icon_tag(want_rel, want_type)
            matches = [link for link in found if link[0] == want_rel and link[1] == want_type]
            if len(matches) != 1:
                error(rel, f"應有一個 {tag}，實得 {[link[3] for link in matches]!r}")
                continue
            _, _, sizes, href = matches[0]
            href = href or ""
            hrefs.setdefault((want_rel, want_type), {})[rel] = href
            if sizes != want_sizes:
                error(rel, f"{tag} 的 sizes 應為 {want_sizes!r}，實得 {sizes!r}")
            if urlsplit(href).path != want_path:
                error(rel, f"{tag} 應指向 {want_path}?v=<版本>，實得 {href!r}")
                continue
            version = url_version(href)
            if not version:
                error(rel, f"{tag} 的網址應帶 ?v= 版本參數，實得 {href!r}")
            versions.add(version)
            if resolve_internal(want_path) is None:
                error(rel, f"{tag} 指向不存在的檔案：{href!r}")
    for (want_rel, want_type), by_page in sorted(hrefs.items(), key=lambda item: str(item[0])):
        if len(set(by_page.values())) > 1:
            detail = "；".join(f"{page} {href!r}" for page, href in sorted(by_page.items()))
            error("site/**/*.html", f"所有頁面的 {icon_tag(want_rel, want_type)} 網址應相同，實得 {detail}")
    # 有 sizes 的 PNG 圖示：實際寬高要與 sizes 相符。
    for _, _, want_sizes, want_path in ICON_LINKS:
        path = want_path.lstrip("/")
        if want_sizes and path.endswith(".png") and (ROOT / path).is_file():
            check_png_matches(path, path, want_sizes)
    return versions


def check_manifest():
    """site.webmanifest 是合法 JSON，欄位符合 EXPECTED_MANIFEST_FIELDS，start_url 指向存在的頁面，
    icons 指向存在的 PNG，實際寬高與 sizes 相符。回傳 icon 用到的版本。"""
    versions = set()
    try:
        data = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error(MANIFEST, f"無法解析 JSON：{exc}")
        return versions
    if not isinstance(data, dict):
        error(MANIFEST, f"最上層應為物件，實得 {type(data).__name__}")
        return versions
    for key, expected in EXPECTED_MANIFEST_FIELDS.items():
        if data.get(key) != expected:
            error(MANIFEST, f"{key} 應為 {expected!r}，實得 {data.get(key)!r}")
    start_url = data.get("start_url")
    if isinstance(start_url, str) and start_url.startswith("/") and resolve_internal(urlsplit(start_url).path) is None:
        error(MANIFEST, f"start_url 指向不存在的頁面：{start_url!r}")
    icons = data.get("icons")
    if not isinstance(icons, list) or not icons:
        error(MANIFEST, f"icons 應為非空陣列，實得 {icons!r}")
        return versions
    coverage = set()  # (purpose, sizes)
    for index, icon in enumerate(icons):
        label = f"{MANIFEST} icons[{index}]"
        if not isinstance(icon, dict):
            error(label, f"應為物件，實得 {icon!r}")
            continue
        src, sizes, kind = icon.get("src"), icon.get("sizes"), icon.get("type")
        if not isinstance(src, str) or not src.startswith("/"):
            error(label, f"src 應為以 / 開頭的站內路徑，實得 {src!r}")
            continue
        version = url_version(src)
        if not version:
            error(label, f"src 應帶 ?v= 版本參數，實得 {src!r}")
        versions.add(version)
        path = urlsplit(src).path.lstrip("/")
        if not (ROOT / path).is_file():
            error(label, f"src 指向不存在的檔案：{src!r}")
            continue
        if kind != "image/png" or not path.endswith(".png"):
            error(label, f"應為 PNG（type \"image/png\"），實得 type {kind!r}、src {src!r}")
            continue
        check_png_matches(label, path, sizes)
        for purpose in str(icon.get("purpose", "any")).split():
            coverage.add((purpose, sizes))
    for purpose in sorted(MANIFEST_PURPOSES):
        missing = sorted(size for size in MANIFEST_SIZES if (purpose, size) not in coverage)
        if missing:
            error(MANIFEST, f"purpose {purpose!r} 缺少 {missing} 的圖示")
    return versions


def check_icon_versions(page_versions, manifest_versions):
    """頁面與 site.webmanifest 的 icon 網址用同一個 ?v=：修改 icon 時一起換掉。"""
    found = (page_versions | manifest_versions) - {""}
    if len(found) > 1:
        error(
            "site/**/*.html、site/site.webmanifest",
            f"icon 與 manifest 網址的 ?v= 應相同，頁面實得 {sorted(page_versions)}，manifest 實得 {sorted(manifest_versions)}",
        )


def embedded_png_length(data, offset):
    """從 offset 的 PNG signature 走過 chunk 到 IEND，回傳 PNG 的長度。找不到 IEND 時回傳 None。"""
    pos = offset + len(PNG_SIGNATURE)
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        chunk = data[pos + 4:pos + 8]
        pos += 12 + length
        if chunk == b"IEND":
            return pos - offset if pos <= len(data) else None
    return None


def check_favicon_svg():
    """site/favicon.svg 與 icons/favicon-16.svg 逐位元組相同：只以 build-icons.py 產生，不手改。"""
    rel = "favicon.svg"
    try:
        site_bytes = (ROOT / rel).read_bytes()
        source_bytes = (REPO / FAVICON_SVG_SOURCE).read_bytes()
    except OSError as exc:
        error(rel, f"無法讀取：{exc}")
        return
    if site_bytes != source_bytes:
        error(
            rel,
            f"應與 {FAVICON_SVG_SOURCE} 逐位元組相同（{len(source_bytes)} bytes），實得 {len(site_bytes)} bytes 且內容不同；"
            "以 python3 web/scripts/build-icons.py 重新產生",
        )


def check_ico():
    """favicon.ico 是 ICO，目錄項包含 ICO_SIZES。每項是寬高與目錄項相符的 PNG，color count 0、reserved 0、
    planes 1、bits per pixel 32，bytes in res 等於內嵌 PNG 的長度。"""
    rel = "favicon.ico"
    try:
        data = (ROOT / rel).read_bytes()
    except OSError as exc:
        error(rel, f"無法讀取：{exc}")
        return
    if len(data) < 6:
        error(rel, f"檔案只有 {len(data)} bytes，不是 ICO")
        return
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or kind != 1:
        error(rel, f"ICONDIR 應為 reserved 0、type 1，實得 reserved {reserved}、type {kind}")
        return
    if len(data) < 6 + 16 * count:
        error(rel, f"目錄有 {count} 項，但檔案只有 {len(data)} bytes")
        return
    sizes = set()
    for index in range(count):
        width, height, colors, reserved, planes, bpp, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * index:22 + 16 * index]
        )
        width, height = width or 256, height or 256
        if width == height:
            sizes.add(width)
        else:
            error(rel, f"第 {index} 項不是正方形：{width}x{height}")
        label = f"{rel} 第 {index} 項（{width}x{height}，位移 {offset}，長度 {size}）"
        fields = {"color count": (colors, 0), "reserved": (reserved, 0), "planes": (planes, 1), "bits per pixel": (bpp, 32)}
        for name, (actual_value, expected_value) in fields.items():
            if actual_value != expected_value:
                error(label, f"{name} 應為 {expected_value}，實得 {actual_value}")
        if offset + size > len(data):
            error(label, f"超出檔案長度 {len(data)} bytes")
            continue
        actual = png_size_of(label, data[offset:offset + 26])
        if actual is None:
            continue
        if actual != (width, height):
            error(label, f"PNG 的實際尺寸為 {actual[0]}x{actual[1]}，與目錄項不符")
        png_length = embedded_png_length(data, offset)
        if png_length != size:
            error(label, f"bytes in res 應等於內嵌 PNG 的長度 {png_length}（到 IEND 結束），實得 {size}")
    if sizes != ICO_SIZES:
        error(rel, f"目錄項的尺寸應為 {sorted(ICO_SIZES)}，實得 {sorted(sizes)}")


def check_pairs(counts):
    for zh, en in PAGE_PAIRS:
        if zh in counts and en in counts and counts[zh] != counts[en]:
            error(f"{zh} ↔ {en}", f"中英頁結構不同：{counts[zh]} ↔ {counts[en]}")


def check_aasa():
    rel = ".well-known/apple-app-site-association"
    path = ROOT / rel
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error(rel, f"無法解析 JSON：{exc}")
        return
    if data != EXPECTED_AASA:
        error(rel, f"內容應為 {json.dumps(EXPECTED_AASA)}，實得 {json.dumps(data)}")


def csp_directives(csp):
    """把 CSP 字串拆成 {directive: 來源字串}。"""
    directives = {}
    for part in csp.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0].lower()] = " ".join(tokens[1:])
    return directives


def check_headers():
    """`site/_headers`：驗證檔以 application/json、manifest 以 application/manifest+json 回應，
    所有頁面帶 CSP 與 no-referrer，/dropbox/oauth/* 另帶嚴格的 CSP。"""
    path = ROOT / "_headers"
    if not path.is_file():
        error("site/_headers", "檔案不存在")
        return
    rules = {}
    current = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # `! Header` 會移除前面規則設定的 header（detach），可能拿掉嚴格的 CSP。
        if line[0].isspace() and line.lstrip().startswith("!"):
            error("site/_headers", f"第 {number} 行不得使用 detach 語法（! Header）：{line.strip()!r}")
            continue
        if not line[0].isspace():
            current = line.strip()
            rules.setdefault(current, {})
        elif current is not None and ":" in line:
            name, value = line.strip().split(":", 1)
            rules[current][name.strip().lower()] = value.strip()
    aasa = rules.get("/.well-known/apple-app-site-association", {})
    if aasa.get("content-type") != "application/json":
        error("site/_headers", "驗證檔應設定 Content-Type: application/json")
    manifest_type = rules.get(f"/{MANIFEST}", {}).get("content-type")
    if manifest_type != "application/manifest+json":
        error("site/_headers", f"/{MANIFEST} 應設定 Content-Type: application/manifest+json，實得 {manifest_type!r}")
    every = rules.get("/*", {})
    csp = every.get("content-security-policy", "")
    expected = EXPECTED_CSP_ANALYTICS + FRAME_ANCESTORS
    if csp != expected:
        error("site/_headers", f"/* 的 Content-Security-Policy 應為 {expected!r}，實得 {csp!r}")
    directives = csp_directives(csp)
    if directives.get("default-src") != "'none'":
        error("site/_headers", f"/* 的 CSP 應有 default-src 'none'，實得 {directives.get('default-src')!r}")
    # Cloudflare 的 JavaScript Detections 注入 inline script 與 /cdn-cgi/challenge-platform/ script，只靠 CSP 擋下。
    if directives.get("script-src") != ANALYTICS_SCRIPT_SRC:
        error(
            "site/_headers",
            f"/* 的 CSP script-src 應只有 {ANALYTICS_SCRIPT_SRC!r}，實得 {directives.get('script-src')!r}",
        )
    if "unsafe" in csp:
        error("site/_headers", f"/* 的 CSP 不得含 unsafe-*，實得 {csp!r}")
    if every.get("referrer-policy") != "no-referrer":
        error("site/_headers", "/* 應設定 Referrer-Policy: no-referrer")
    oauth = rules.get("/dropbox/oauth/*", {})
    if oauth.get("cache-control") != "no-store":
        error("site/_headers", "/dropbox/oauth/* 應設定 Cache-Control: no-store")
    # 這條與 /* 的 CSP 同時生效（取交集），網址帶授權碼的回呼頁因此不執行任何 script。
    oauth_csp = oauth.get("content-security-policy")
    oauth_expected = EXPECTED_CSP_STRICT + FRAME_ANCESTORS
    if oauth_csp is None:
        error("site/_headers", f"/dropbox/oauth/* 缺少 Content-Security-Policy，應為 {oauth_expected!r}")
    elif oauth_csp != oauth_expected:
        error(
            "site/_headers",
            f"/dropbox/oauth/* 的 Content-Security-Policy 應為 {oauth_expected!r}，實得 {oauth_csp!r}",
        )


def check_css():
    for path in sorted((ROOT / "assets").glob("*.css")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8").lower()
        for needle in ("http://", "https://", "@import", "url("):
            if needle in text:
                error(rel, f"含有 {needle}，CSS 不得載入其他資源")


def check_yaml():
    files = sorted((REPO / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    ruby = shutil.which("ruby")
    if ruby is None:
        print("略過：找不到 ruby，未解析 Issue 表單的 YAML")
        return
    script = (
        "require 'yaml'; require 'json'; "
        "puts JSON.generate(ARGV.to_h { |f| [f, YAML.safe_load(File.read(f))] })"
    )
    result = subprocess.run(
        [ruby, "-e", script, *[str(f) for f in files]],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        error(".github/ISSUE_TEMPLATE", f"YAML 解析失敗：{result.stderr.strip()}")
        return
    docs = json.loads(result.stdout)
    for name, doc in docs.items():
        rel = Path(name).relative_to(REPO).as_posix()
        if rel.endswith("config.yml"):
            if doc.get("blank_issues_enabled") is not False:
                error(rel, "blank_issues_enabled 應為 false")
            continue
        body = doc.get("body") or []
        first = body[0] if body else {}
        value = (first.get("attributes") or {}).get("value", "")
        if first.get("type") != "markdown" or "不要貼上密碼" not in value:
            error(rel, "表單第一個元素應為含隱私警語的 markdown")
        ids = [item.get("id") for item in body if item.get("id")]
        if len(ids) != len(set(ids)):
            error(rel, "表單元素的 id 重複")
    print(f"YAML：{len(docs)} 個 Issue 表單以 {ruby} 解析")


def main():
    html_files = sorted(p for p in ROOT.rglob("*.html") if ".git" not in p.parts)
    counts = {}
    stylesheets = {}
    icons = {}
    for path in html_files:
        rel, page_counts, page_stylesheets, page_icons = check_html(path)
        counts[rel] = page_counts
        stylesheets[rel] = page_stylesheets
        icons[rel] = page_icons
    print(f"HTML：檢查 {len(html_files)} 個檔案")
    for rel in sorted(counts):
        print(f"  {rel} {counts[rel]}")
    check_pairs(counts)
    check_stylesheets(stylesheets)
    check_icon_versions(check_icons(icons), check_manifest())
    check_ico()
    check_favicon_svg()
    check_css()
    check_aasa()
    check_headers()
    check_yaml()

    if errors:
        print(f"\n{len(errors)} 個錯誤：")
        for line in errors:
            print(f"  {line}")
        sys.exit(1)
    print("\n全部通過")


if __name__ == "__main__":
    main()
