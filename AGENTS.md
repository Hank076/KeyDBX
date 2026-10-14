# AGENTS.md

適用於所有 AI coding agent。這個目錄放 KeyDBX 的網站與 Issue 表單，位於 App repo 的 `web/`，以 `git subtree` 發布到公開 repo `Hank076/KeyDBX`。網站結構與發布設定見 [README.md](README.md)。agent 規範採用與 Git 慣例以 App repo 根目錄的 `AGENTS.md` 為準。

## 約束

- 網站檔案只放在 `site/`：Cloudflare Pages 只發布這個目錄，公開 repo 的其他檔案（開發文件、腳本）不會出現在網站上。
- 頁面只用靜態 HTML 與 `site/assets/site.css`，網站本身不寫 JavaScript，除了 Cloudflare Web Analytics 不載入外部資源（字型、CDN、追蹤、嵌入）：外部資源可能把網址送出去，隱私政策只揭露 Web Analytics。
- 修改 `site/assets/site.css` 時，所有頁面 stylesheet 連結（`/assets/site.css?v=<版本>`）的 `?v=` 一起改成新值，例如修改當天的日期 `20261014`，同一天第二次改成 `20261014-2`：Cloudflare 讓瀏覽器快取 CSS 4 小時，網址不變時訪客會用舊 CSS 配新 HTML。
- 每頁保留 `<meta name="referrer" content="no-referrer">` 與 Content-Security-Policy meta，`site/_headers` 對所有路徑（`/*`）送出 CSP 與 `Referrer-Policy: no-referrer`：瀏覽器因此擋下未放行的 script 與外部資源，點出站外連結時也不送出網址。meta 在本機預覽時也生效，header 另外涵蓋 meta 做不到的 `frame-ancestors`。各頁 meta 與 `_headers` 的 CSP 字串以 `scripts/check-site.py` 的 `EXPECTED_CSP_ANALYTICS`、`EXPECTED_CSP_STRICT` 為準。
- 一般頁面 CSP 的 `script-src` 只放行 `https://static.cloudflareinsights.com`，`connect-src` 只放行 `'self'` 與 `https://cloudflareinsights.com`；不得使用 `unsafe-inline`、`unsafe-eval`，`script-src` 不加 `'self'`：Cloudflare 免費方案的 JavaScript Detections 只能對整個網域開關（`hankchen.info` 已確認開啟；`lab076.dev` 的設定尚未確認，當作開啟處理），它注入的 inline script 與 `/cdn-cgi/challenge-platform/` 的 script 只靠 CSP 擋下。
- `/dropbox/oauth/` 的 meta CSP 與 `_headers` 的 `/dropbox/oauth/*` CSP 都維持嚴格版本，不含 `script-src`、`connect-src`：網址帶 OAuth 授權碼，analytics 的 script 會讀取頁面網址。`_headers` 的 `/*` 與 `/dropbox/oauth/*` 兩條 CSP 都要保留：Pages 以逗號串接同名 header，瀏覽器同時套用兩個 policy，嚴格的那條讓 `/*` 的放行不適用這頁。`_headers` 不使用 detach 語法（`! Header`）：它會移除前面規則設定的 header。
- `404.html` 的 meta CSP 也用嚴格版本：`_headers` 的路徑比對分大小寫，`/Dropbox/OAuth/?code=…` 這類網址由 `404.html` 回應且只套用 `/*`，放行 analytics 時 beacon 會讀到含授權碼的網址。
- Cloudflare 的 Web Analytics 允許開啟；Email Address Obfuscation、Rocket Loader 不得開啟：它們注入的 script 只有放寬 CSP（`'self'` 或 `unsafe-inline`）才能執行，而且 Rocket Loader 會改寫頁面 script 的 `type`（包括 beacon），開啟後 beacon 不會執行。Web Analytics 只對瀏覽器的 User-Agent 注入，檢查方式見 README「驗證檔檢查」。
- 隱私政策（`site/privacy/`、`site/en/privacy/`）的「這個網站」一節描述 Web Analytics 收集的資料。變更 Cloudflare 的分析設定時，一併更新隱私政策與生效日期：隱私政策是對使用者的承諾。
- `site/dropbox/oauth/index.html` 不得讀取或顯示網址參數，並保留 `noindex`；`site/_headers` 對這個路徑送出 `Cache-Control: no-store`：網址參數是 OAuth 授權碼。
- `site/_headers` 保留驗證檔的 `Content-Type: application/json`：驗證檔沒有副檔名，iOS 要求以 JSON 回應。
- `site/.well-known/apple-app-site-association` 的 Team ID（`NQ5QFN5794`）與 bundle ID（`dev.lab076.KeyDBX`）必須與 App 的 `KeyDBX.xcodeproj/project.pbxproj` 一致：不一致時 iOS 不承認這個網域。
- 中文頁與英文頁的內容必須同步：同一份政策或說明不能有兩種內容。修改一頁時，同時修改另一種語言的對應頁。
- 隱私政策、介紹頁與支援頁的每一項敘述，都要能對照 App repo 的程式或文件：隱私政策是對使用者的承諾。
- 網站的待辦與踩坑紀錄寫進 App repo 根目錄的 `docs/handover.md` 與 `docs/project_postmortem.md`，不放進 `web/`：公開 repo 會包含 `web/` 的所有提交檔案。`web/.gitignore` 排除 `docs/`，防止誤提交。
- Issue 表單最上方保留隱私警語（不要貼密碼、資料庫、主密碼、金鑰檔、TOTP 密鑰）：Issue 是公開的。
- 站內連結用以 `/` 開頭的絕對路徑：`404.html` 會回應任何深度的不存在路徑，相對路徑在那裡會失效。
- 提到 KeePass、KeePassXC、Dropbox、Apple 的頁面保留商標聲明，不使用它們的 logo。

## 驗證指令

在 App repo 根目錄執行：

```bash
python3 web/scripts/check-site.py
```

## 發布

`web/` 的內容與修改 `web/` 的 commit message 都會公開。修改 `web/` 時單獨 commit，不與 App 的變更放在同一個 commit：`git subtree split` 會把這些 commit 帶到公開 repo。

公開 repo 的 `main` 推送後會直接發布網站。在 App repo 根目錄執行，且需使用者明確要求：

```bash
git subtree push --prefix=web site main
```

`site` remote 指向 `https://github.com/Hank076/KeyDBX.git`。clone 後沒有這個 remote 時，先執行 `git remote add site https://github.com/Hank076/KeyDBX.git`。
