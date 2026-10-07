#!/usr/bin/env python3
"""檢查 KeyDBX 網站的靜態檔案（`site/`，Cloudflare Pages 的輸出目錄）。在 App repo 根目錄執行：python3 web/scripts/check-site.py

有任何錯誤時以結束碼 1 結束。每則錯誤包含檔案路徑與原因。
"""

import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

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

EXPECTED_CSP = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"
EXPECTED_AASA = {"webcredentials": {"apps": ["NQ5QFN5794.dev.lab076.KeyDBX"]}}

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
        self.counts = {"h2": 0, "li": 0, "details": 0}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.html_lang = attrs.get("lang")
        if tag == "meta":
            self.metas.append(attrs)
        if tag == "link" and attrs.get("rel") == "alternate":
            self.alternates.append((attrs.get("hreflang"), attrs.get("href")))
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
    if metas.get("Content-Security-Policy") != EXPECTED_CSP:
        error(rel, f"CSP meta 應為 {EXPECTED_CSP!r}，實得 {metas.get('Content-Security-Policy')!r}")

    for tag, attr, value in parser.links:
        check_link(rel, tag, attr, value)

    if rel not in NO_HREFLANG:
        langs = {lang for lang, _ in parser.alternates}
        if langs != {"zh-Hant-TW", "en"}:
            error(rel, f"hreflang 應為 zh-Hant-TW 與 en，實得 {sorted(l for l in langs if l)}")

    if rel == "dropbox/oauth/index.html":
        if metas.get("robots") != "noindex":
            error(rel, "缺少 <meta name=\"robots\" content=\"noindex\">")
        for word in ("location", "search", "code="):
            if word in lowered:
                error(rel, f"不得處理網址參數，發現 {word!r}")

    return rel, parser.counts


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


def check_headers():
    """`site/_headers`：驗證檔以 application/json 回應，所有頁面帶 CSP 與 no-referrer。"""
    path = ROOT / "_headers"
    if not path.is_file():
        error("site/_headers", "檔案不存在")
        return
    rules = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
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
    every = rules.get("/*", {})
    csp = every.get("content-security-policy", "")
    if "default-src 'none'" not in csp:
        error("site/_headers", "/* 應設定 Content-Security-Policy（default-src 'none'）")
    # Cloudflare 的 JavaScript Detections 注入 inline script，只靠 CSP 擋下。
    if "script-src" in csp or "unsafe" in csp:
        error("site/_headers", "CSP 不得放行 script（script-src、unsafe-inline、unsafe-eval）")
    if every.get("referrer-policy") != "no-referrer":
        error("site/_headers", "/* 應設定 Referrer-Policy: no-referrer")
    oauth = rules.get("/dropbox/oauth/*", {})
    if oauth.get("cache-control") != "no-store":
        error("site/_headers", "/dropbox/oauth/* 應設定 Cache-Control: no-store")


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
    for path in html_files:
        rel, page_counts = check_html(path)
        counts[rel] = page_counts
    print(f"HTML：檢查 {len(html_files)} 個檔案")
    for rel in sorted(counts):
        print(f"  {rel} {counts[rel]}")
    check_pairs(counts)
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
