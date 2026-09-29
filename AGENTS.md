# AGENTS.md

適用於所有 AI coding agent。這個 repo 只放 KeyDBX 的網站與 Issue 表單，App 原始碼在另一個私人 repo。網站結構與發布設定見 [README.md](README.md)。

## agent 規範採用

- `sdd-workflow`：不採用
- `feature-wrapup`：採用
- `git-workflow`：採用

## 約束

- 網站檔案只放在 `site/`：Cloudflare Pages 只發布這個目錄，repo 的其他檔案（開發文件、腳本）不會出現在網站上。
- 頁面只用靜態 HTML 與 `site/assets/site.css`，不用 JavaScript，也不載入任何外部資源（字型、CDN、分析、追蹤、嵌入）：`/dropbox/oauth/` 的網址帶有 OAuth 授權碼，外部資源可能把網址送出去；隱私政策也承諾網站不追蹤。
- 每頁保留 `<meta name="referrer" content="no-referrer">` 與 Content-Security-Policy meta（`default-src 'none'; style-src 'self'; img-src 'self'`），`site/_headers` 也對所有路徑送出相同的 CSP 與 `Referrer-Policy: no-referrer`：瀏覽器因此擋下 script 與外部資源，點出站外連結時也不送出網址。meta 在本機預覽時也生效，header 另外涵蓋 meta 做不到的 `frame-ancestors`。
- CSP 不得加入 `script-src`，也不得使用 `unsafe-inline` 或 `unsafe-eval`：Cloudflare 免費方案的 JavaScript Detections 對整個 `hankchen.info` 網域開啟，無法只對這個子網域關閉，它注入的 inline script 只靠 CSP 擋下；放寬後注入的 script 就會執行，而 `/dropbox/oauth/` 的網址帶有授權碼。
- 不得開啟其他會注入 script 的 Cloudflare 功能（Web Analytics、Email Address Obfuscation、Rocket Loader）：網站承諾不使用 JavaScript，隱私政策也承諾沒有分析。Web Analytics 只對瀏覽器的 User-Agent 注入，檢查方式見 README「驗證檔檢查」。
- `site/dropbox/oauth/index.html` 不得讀取或顯示網址參數，並保留 `noindex`；`site/_headers` 對這個路徑送出 `Cache-Control: no-store`：網址參數是 OAuth 授權碼。
- `site/_headers` 保留驗證檔的 `Content-Type: application/json`：驗證檔沒有副檔名，iOS 要求以 JSON 回應。
- `site/.well-known/apple-app-site-association` 的 Team ID（`MGH5T96U79`）與 bundle ID（`com.hank.KeyDBX`）必須與 App repo 的 `project.pbxproj` 一致：不一致時 iOS 不承認這個網域。
- 中文頁與英文頁的內容必須同步：同一份政策或說明不能有兩種內容。修改一頁時，同時修改另一種語言的對應頁。
- 隱私政策、介紹頁與支援頁的每一項敘述，都要能對照 App repo 的程式或文件：隱私政策是對使用者的承諾。
- 開發用的文件（待辦與交接 `docs/handover.md`、踩坑紀錄等）放在 `docs/`，只留在本機，不提交（`.gitignore`）：repo 公開。
- Issue 表單最上方保留隱私警語（不要貼密碼、資料庫、主密碼、金鑰檔、TOTP 密鑰）：Issue 是公開的。
- 站內連結用以 `/` 開頭的絕對路徑：`404.html` 會回應任何深度的不存在路徑，相對路徑在那裡會失效。
- 提到 KeePass、KeePassXC、Dropbox、Apple 的頁面保留商標聲明，不使用它們的 logo。

## 驗證指令

```bash
python3 scripts/check-site.py
```

## Git

採 GitHub Flow。分支名格式為 `<type>/<英文簡述>_<session 短碼>`。commit message 用 Conventional Commits，body 寫約束與影響。

commit 時以明確檔案路徑 `git add`，不使用 `git add -A`：工作目錄可能有並行任務的檔案。

推送到 `main` 會直接發布網站。push、merge 到 `main` 需使用者明確要求。
