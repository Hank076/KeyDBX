# KeyDBX 網站

這個 repo 只放 KeyDBX 的網站與問題回報，不含 App 原始碼。內容來自 App repo 的 `web/` 目錄，以 `git subtree push --prefix=web site main` 推送到這個 repo。網站由 Cloudflare Pages 從 `main` 分支部署，只發布 `site/` 目錄，網址為 <https://keydbx.lab076.dev/>。

## 網址

| 路徑 | 內容 |
| --- | --- |
| `/`、`/en/` | 介紹頁（正體中文、英文） |
| `/privacy/`、`/en/privacy/` | 隱私政策 |
| `/support/`、`/en/support/` | 常見問題、問題回報、安全問題的私下回報 |
| `/dropbox/oauth/` | Dropbox 登入回呼的備援頁 |
| `/.well-known/apple-app-site-association` | Apple 的 associated domains 驗證檔 |

問題回報：<https://github.com/Hank076/KeyDBX/issues>。安全問題：<https://github.com/Hank076/KeyDBX/security/advisories/new>。

## 目錄結構

```
./
├─ site/                          # Cloudflare Pages 的輸出目錄，只有這個目錄會發布
│  ├─ index.html                  # 正體中文介紹頁
│  ├─ en/                         # 英文頁面：index.html、privacy/、support/
│  ├─ privacy/index.html          # 隱私政策
│  ├─ support/index.html          # 支援
│  ├─ dropbox/oauth/index.html    # Dropbox 登入回呼的備援頁
│  ├─ 404.html                    # 找不到頁面（中英並列）
│  ├─ assets/site.css             # 共用樣式
│  ├─ favicon.svg、favicon.ico、favicon-96x96.png   # 瀏覽器分頁圖示（build-icons.py 產生）
│  ├─ apple-touch-icon.png        # iOS 主畫面圖示（build-icons.py 產生）
│  ├─ web-app-manifest-192x192.png、web-app-manifest-512x512.png   # manifest 圖示（build-icons.py 產生）
│  ├─ site.webmanifest            # web app manifest
│  ├─ .well-known/apple-app-site-association
│  └─ _headers                    # 回應 header：CSP、驗證檔與 manifest 的 Content-Type
├─ icons/                         # 圖示的原始 SVG，不發布：favicon-16.svg、favicon-64.svg、icon-full.svg
├─ scripts/
│  ├─ check-site.py               # 網站檢查
│  └─ build-icons.py              # 從 icons/ 產生 site/ 的圖示
└─ .github/
   ├─ ISSUE_TEMPLATE/             # Issue 表單：問題回報、功能建議、聯絡連結
   └─ SECURITY.md                 # 安全問題的回報方式
```

## 本機預覽

在 `web/` 目錄執行：

```bash
python3 -m http.server 8000 --directory site
```

開啟 <http://localhost:8000/>。`http.server` 不讀取 `_headers`，也不使用 `404.html`。

## 檢查

在 App repo 根目錄執行：

```bash
python3 web/scripts/check-site.py
```

檢查項目：HTML 標籤成對、站內連結指向存在的檔案、所有頁面的 stylesheet 網址相同且帶 `?v=` 版本參數、每頁都有 icon 與 manifest 的 `<link>` 與 `apple-mobile-web-app-title`（網址在所有頁面相同、帶 `?v=` 且指向存在的檔案，頁面與 `site.webmanifest` 的 icon 用同一個 `?v=`）、`site.webmanifest` 可解析且每個 icon 的 PNG 實際寬高與 `sizes` 相符（`any` 與 `maskable` 都有 192 與 512）、`favicon-96x96.png` 與 `apple-touch-icon.png` 的實際寬高、`favicon.ico` 含 16、32、48 三種尺寸、沒有 `<script`、沒有 `http://`、外部連結只指向允許的網域、每頁的 `lang`、`hreflang`、`referrer` 與 CSP meta（`/dropbox/oauth/` 與 `404.html` 用不放行 script 的嚴格版，其他頁放行 Web Analytics）、`_headers` 的必要規則（`/site.webmanifest` 的 `Content-Type: application/manifest+json`、`/*` 的 `script-src` 只有 `https://static.cloudflareinsights.com`、不含 `unsafe`，`/dropbox/oauth/*` 另有嚴格的 CSP，不使用 detach 語法 `! Header`）、驗證檔與 Issue 表單可解析。Issue 表單的 YAML 以 `ruby -ryaml` 解析，沒有 Ruby 時略過並顯示提示。

## 重產圖示

修改 `icons/` 的 SVG 後，在 App repo 根目錄執行：

```bash
python3 web/scripts/build-icons.py
```

腳本需要 Google Chrome（`/Applications/Google Chrome.app`），以 headless Chrome 截圖產生 PNG，再把 16、32、48 三張 PNG 包成 `favicon.ico`。所有產出驗證通過後才寫入 `site/`，失敗時 `site/` 不變。同一個 Chrome 版本重複執行時，產出逐位元組相同；Chrome 版本不同時，PNG 的位元組可能不同。沒有修改 `icons/` 時不要重產：產出改變會讓 `site/` 出現沒有意義的差異。

| 原始檔 | 產出 |
| --- | --- |
| `icons/favicon-16.svg` | `favicon.svg`、`favicon.ico` 的 16px |
| `icons/favicon-64.svg` | `favicon.ico` 的 32、48px、`favicon-96x96.png` |
| `icons/icon-full.svg` | `apple-touch-icon.png`（180）、`web-app-manifest-192x192.png`、`web-app-manifest-512x512.png` |

`icon-full.svg` 滿版不留圓角：iOS 與 maskable icon 由系統套用形狀，圖案在 maskable 的安全區（中心半徑 40%）內。產生後依 `web/AGENTS.md` 更新各頁與 `site.webmanifest` 的 icon `?v=`，再執行檢查。

## Cloudflare Pages 設定

DNS 在 Cloudflare。推送到 `main` 會直接部署到正式網站；其他分支部署到預覽網址。

1. 在 Cloudflare 的 **Workers & Pages** → **Create** → **Pages** → **Connect to Git**，授權 GitHub 時只允許存取 `Hank076/KeyDBX`。
2. 建置設定：
   - **Production branch**：`main`
   - **Framework preset**：None
   - **Build command**：留空
   - **Build output directory**：`site`
3. 部署完成後，在專案的 **Custom domains** 加入 `keydbx.lab076.dev`。DNS 已有 `keydbx` 的其他紀錄時，先刪除它，再讓 Pages 建立新的紀錄。
4. **Web Analytics** 可以在 Pages 專案的 **Metrics** 頁開啟。開啟後，Cloudflare 對瀏覽器的 User-Agent 在頁面注入 `static.cloudflareinsights.com/beacon.min.js`（`curl` 預設的 User-Agent 不會被注入），網站的 CSP 放行這個 script 與它送出統計的連線；`/dropbox/oauth/` 與 `404.html` 的 CSP 不放行，beacon 在這兩頁不執行。在網域的設定關閉 **Email Address Obfuscation** 與 **Rocket Loader**：它們注入的 script 不在 CSP 放行範圍內。Bot Fight Mode 的 **JavaScript Detections** 也會注入 script（載入 `/cdn-cgi/challenge-platform/scripts/jsd/main.js`），但免費方案只能對整個網域開關，所以不論 `lab076.dev` 是否開啟，都由網站的 CSP 擋下它執行。
5. 確認 **Bot Fight Mode** 與 challenge 規則不會擋下 `/.well-known/*`。擋下時，Apple CDN 取不到驗證檔。
6. 在 GitHub repo 的 **Settings → Security**（Code security）開啟 **Private vulnerability reporting**。

## 驗證檔檢查

確認回應為 200、`content-type: application/json`，而且沒有轉址：

```bash
curl -sI https://keydbx.lab076.dev/.well-known/apple-app-site-association
```

確認一般頁面的 CSP 只放行 Web Analytics 的 script。結果應為一行 `script-src https://static.cloudflareinsights.com`：

```bash
curl -sI https://keydbx.lab076.dev/ | grep -i "^content-security-policy" | grep -o "script-src [^;]*"
```

確認一般頁面的 CSP 沒有 `unsafe-inline`、`unsafe-eval`（結果應為 0）。頁面原始碼中的 JavaScript Detections script 會被這個 CSP 擋下：

```bash
curl -sI https://keydbx.lab076.dev/ | grep -i "^content-security-policy" | grep -c -i "unsafe"
```

確認 Web Analytics 的 beacon 來自 `static.cloudflareinsights.com`。要帶瀏覽器的 User-Agent，Cloudflare 才會注入。結果應為一行，開頭是 `src="https://static.cloudflareinsights.com/beacon.min.js`（引號可能是單引號）；沒有輸出代表 Web Analytics 沒有開啟：

```bash
curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1" -H "Accept: text/html" https://keydbx.lab076.dev/ | grep -Eo "src=[\"'][^\"']*beacon\.min\.js"
```

確認 Dropbox 回呼頁送出不放行 script 的嚴格 CSP（結果應為 1）。Pages 把 `/*` 與 `/dropbox/oauth/*` 的 CSP 以逗號串接在同一個 header，瀏覽器同時套用兩個 policy：

```bash
curl -sI https://keydbx.lab076.dev/dropbox/oauth/ | grep -i "^content-security-policy" | grep -c "default-src 'none'; style-src 'self'; img-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
```

確認 manifest 以 manifest 的 MIME type 回應。結果應為一行 `content-type: application/manifest+json`：

```bash
curl -sI https://keydbx.lab076.dev/site.webmanifest | grep -i "^content-type"
```

部署後在瀏覽器確認 favicon 與 manifest：

1. 用桌面版 Chrome 開啟 <https://keydbx.lab076.dev/>，開啟開發者工具，重新載入頁面。
2. 確認分頁顯示 KeyDBX 的圖示，**Console** 沒有 favicon 或 manifest 的 CSP 錯誤（`Refused to load` 加上 `img-src` 或 `manifest-src`）。
3. 在 **Application** → **Manifest** 確認讀到 `site.webmanifest`，名稱為 KeyDBX，**Icons** 顯示 192 與 512 的圖示。
4. 開啟 <https://keydbx.lab076.dev/dropbox/oauth/>，重複第 2 步。

部署後在瀏覽器確認 Web Analytics 有送出資料：

1. 用桌面版 Safari 或 Chrome 開啟 <https://keydbx.lab076.dev/>。
2. 開啟開發者工具的 **Network**（網路）分頁，重新載入頁面。
3. 確認 `beacon.min.js` 載入成功，而且送往 `/cdn-cgi/rum`（或 `https://cloudflareinsights.com/cdn-cgi/rum`）的請求回應 2xx。**Console** 不應出現 CSP 擋下 beacon 的錯誤。
4. 到 Cloudflare dashboard 的 **Web Analytics**，確認 `keydbx.lab076.dev` 有資料。

`/cdn-cgi/rum` 的請求失敗或 dashboard 收不到資料時，先檢查 `Referrer-Policy: no-referrer`：Cloudflare 的 Web Analytics FAQ 寫明 `Referer` header 是必要的；beacon 以 CORS 送出時仍帶 `Origin` header。調整 `Referrer-Policy` 時只放寬一般頁面，`/dropbox/oauth/` 與 `404.html` 維持 `no-referrer`。

確認 Apple CDN 取得的內容與 `site/.well-known/apple-app-site-association` 相同：

```bash
curl https://app-site-association.cdn-apple.com/a/v1/keydbx.lab076.dev
```

Apple CDN 會快取驗證檔。修改後要等 CDN 更新，才會反映在上面的結果。
