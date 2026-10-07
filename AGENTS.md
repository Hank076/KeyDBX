# AGENTS.md

適用於所有 AI coding agent。這個目錄放 KeyDBX 的網站與 Issue 表單，位於 App repo 的 `web/`，以 `git subtree` 發布到公開 repo `Hank076/KeyDBX`。網站結構與發布設定見 [README.md](README.md)。agent 規範採用與 Git 慣例以 App repo 根目錄的 `AGENTS.md` 為準。

## 約束

- 網站檔案只放在 `site/`：Cloudflare Pages 只發布這個目錄，公開 repo 的其他檔案（開發文件、腳本）不會出現在網站上。
- 頁面只用靜態 HTML 與 `site/assets/site.css`，不用 JavaScript，也不載入任何外部資源（字型、CDN、分析、追蹤、嵌入）：`/dropbox/oauth/` 的網址帶有 OAuth 授權碼，外部資源可能把網址送出去；隱私政策也承諾網站不追蹤。
- 每頁保留 `<meta name="referrer" content="no-referrer">` 與 Content-Security-Policy meta（`default-src 'none'; style-src 'self'; img-src 'self'`），`site/_headers` 也對所有路徑送出相同的 CSP 與 `Referrer-Policy: no-referrer`：瀏覽器因此擋下 script 與外部資源，點出站外連結時也不送出網址。meta 在本機預覽時也生效，header 另外涵蓋 meta 做不到的 `frame-ancestors`。
- CSP 不得加入 `script-src`，也不得使用 `unsafe-inline` 或 `unsafe-eval`：Cloudflare 免費方案的 JavaScript Detections 只能對整個網域開關，無法只對這個子網域關閉（`hankchen.info` 已確認開啟；`lab076.dev` 的設定尚未確認，當作開啟處理），它注入的 inline script 只靠 CSP 擋下；放寬後注入的 script 就會執行，而 `/dropbox/oauth/` 的網址帶有授權碼。
- 不得開啟其他會注入 script 的 Cloudflare 功能（Web Analytics、Email Address Obfuscation、Rocket Loader）：網站承諾不使用 JavaScript，隱私政策也承諾沒有分析。Web Analytics 只對瀏覽器的 User-Agent 注入，檢查方式見 README「驗證檔檢查」。
- `site/dropbox/oauth/index.html` 不得讀取或顯示網址參數，並保留 `noindex`；`site/_headers` 對這個路徑送出 `Cache-Control: no-store`：網址參數是 OAuth 授權碼。
- `site/_headers` 保留驗證檔的 `Content-Type: application/json`：驗證檔沒有副檔名，iOS 要求以 JSON 回應。
- `site/.well-known/apple-app-site-association` 的 Team ID（`NQ5QFN5794`）與 bundle ID（`dev.lab076.KeyDBX`）必須與 App 的 `KeyDBX.xcodeproj/project.pbxproj` 一致：不一致時 iOS 不承認這個網域。
- 中文頁與英文頁的內容必須同步：同一份政策或說明不能有兩種內容。修改一頁時，同時修改另一種語言的對應頁。
- 隱私政策、介紹頁與支援頁的每一項敘述，都要能對照 App repo 的程式或文件：隱私政策是對使用者的承諾。
- 開發用的文件（待辦與交接 `docs/handover.md`、踩坑紀錄等）放在 `docs/`，只留在本機，不提交（`web/.gitignore`）：公開 repo 會包含 `web/` 的所有提交檔案。
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
