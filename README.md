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
│  ├─ .well-known/apple-app-site-association
│  └─ _headers                    # 回應 header：CSP、驗證檔的 Content-Type
├─ scripts/check-site.py          # 網站檢查
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

檢查項目：HTML 標籤成對、站內連結指向存在的檔案、沒有 `<script`、沒有 `http://`、外部連結只指向允許的網域、每頁的 `lang`、`hreflang` 與 `referrer`、`_headers` 的必要規則、驗證檔與 Issue 表單可解析。Issue 表單的 YAML 以 `ruby -ryaml` 解析，沒有 Ruby 時略過並顯示提示。

## Cloudflare Pages 設定

DNS 在 Cloudflare。推送到 `main` 會直接部署到正式網站；其他分支部署到預覽網址。

1. 在 Cloudflare 的 **Workers & Pages** → **Create** → **Pages** → **Connect to Git**，授權 GitHub 時只允許存取 `Hank076/KeyDBX`。
2. 建置設定：
   - **Production branch**：`main`
   - **Framework preset**：None
   - **Build command**：留空
   - **Build output directory**：`site`
3. 部署完成後，在專案的 **Custom domains** 加入 `keydbx.lab076.dev`。DNS 已有 `keydbx` 的其他紀錄時，先刪除它，再讓 Pages 建立新的紀錄。
4. 關閉這個網站的 **Web Analytics**：在 Pages 專案的 **Metrics** 頁關閉 Web Analytics；帳號的 **Web Analytics** 清單中若有 `keydbx.lab076.dev`，也一併刪除或停用自動設定。它會對瀏覽器注入 `static.cloudflareinsights.com/beacon.min.js`（`curl` 預設的 User-Agent 不會被注入）。在網域的設定關閉 **Email Address Obfuscation** 與 **Rocket Loader**：它們會在頁面注入 script。Bot Fight Mode 的 **JavaScript Detections** 也會注入 script（載入 `/cdn-cgi/challenge-platform/scripts/jsd/main.js`），但免費方案只能對整個網域開關，所以不論 `lab076.dev` 是否開啟，都由網站的 CSP 擋下它執行。
5. 確認 **Bot Fight Mode** 與 challenge 規則不會擋下 `/.well-known/*`。擋下時，Apple CDN 取不到驗證檔。
6. 在 GitHub repo 的 **Settings → Security**（Code security）開啟 **Private vulnerability reporting**。

## 驗證檔檢查

確認回應為 200、`content-type: application/json`，而且沒有轉址：

```bash
curl -sI https://keydbx.lab076.dev/.well-known/apple-app-site-association
```

確認正式網站送出的 CSP 沒有放行 script（結果應為 0）。頁面原始碼中的 JavaScript Detections script 會被這個 CSP 擋下：

```bash
curl -sI https://keydbx.lab076.dev/dropbox/oauth/ | grep -i "^content-security-policy" | grep -c -i -e "script-src" -e "unsafe"
```

確認沒有被注入 Web Analytics（結果應為 0）。要帶瀏覽器的 User-Agent，Cloudflare 才會注入：

```bash
curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1" -H "Accept: text/html" https://keydbx.lab076.dev/ | grep -c cloudflareinsights
```

確認 Apple CDN 取得的內容與 `site/.well-known/apple-app-site-association` 相同：

```bash
curl https://app-site-association.cdn-apple.com/a/v1/keydbx.lab076.dev
```

Apple CDN 會快取驗證檔。修改後要等 CDN 更新，才會反映在上面的結果。
