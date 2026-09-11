# Trae 每日签到助手（TRAE-Automatic-sign-in）

> 作者：**星梦**

一个用于 **Trae** 每日积分自动签到的 Windows 桌面小工具。它可以挂在桌面 / 后台运行，每天到点自动签到，并实时显示剩余积分与今日签到状态。

![C#](https://img.shields.io/badge/C%23-.NET%209-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-green)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)

---

## 打个小广告喵：

- TraeSwitch：这是一个用于在 TRAE 多个账号之间「冷切换」的 Windows 桌面小工具。
- 大概功能为：先为每个账号建档一份登录态备份，之后无需验证码即可一键切换到目标账号，并内置「切换守护」在切换失败时自动回滚。
- 项目已开源到：https://github.com/star620/Trea-Switch 各位大佬点点star谢谢喵！

## 功能特性

- **每日自动签到**：到设定时间自动执行签到，无需手动操作。
- **手动签到**：侧边栏或系统托盘均可一键「立即签到」。
- **签到记录**：本地记录每次成功签到的时间与积分（`history.txt`）。
- **系统托盘驻留**：关闭窗口自动最小化到托盘，后台继续自动签到。
- **开机自启动**：可设置登录 Windows 后自动启动本程序。
- **Token 查看与复制**：设置页显示当前 token 及最后更新时间，支持一键复制。
- **内嵌登录**：首次使用 WebView2 内嵌浏览器登录一次，登录态自动保存，后续无需重复登录。
- **云端自动签到（GitHub Actions）**：可一键把签到脚本部署到自己的 GitHub 仓库，无需本机挂机，由 GitHub 每天定时自动签到。
- **单实例运行**：仅允许启动一个实例，再次点击图标会自动唤起已运行的窗口。
- **启动器依赖检查**：独立启动器（自包含，无需 .NET）启动时自动检测 .NET 9 桌面运行时与 WebView2 Runtime，缺失时自动补全或引导安装。

---

## 程序运行原理

程序是一个 **C# WinForms** 桌面应用（.NET 9 + WebView2），运行流程如下：

```
┌─────────────────────────────────────────────────────────────┐
│                      程序启动                                 │
│  读取本地配置 %APPDATA%\TraeCheckin\config.json (含 token)   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  是否需要登录？                                              │
│  ├─ 无 token / token 失效 ──► 弹出 WebView2 内嵌登录窗口     │
│  │                            用户登录一次                   │
│  │                            从 localStorage 读取 token     │
│  │                            保存到本地配置                 │
│  └─ 有有效 token ────────────► 直接进入主界面                │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  启动自动签到定时器（每 10 秒检查一次）                       │
│  到达设定时间且当天未签到 ──► 调用签到接口                   │
│  窗口关闭 ──► 最小化到系统托盘，后台继续运行                 │
└─────────────────────────────────────────────────────────────┘
```

核心组件：

| 文件 | 作用 |
|------|------|
| `Program.cs` | 程序入口，启动主窗体 |
| `Forms/MainForm.cs` | 主界面、自动签到定时器、UI 交互、托盘 |
| `Forms/MainForm.Cloud.cs` | 「云端签到」页（授权与一键部署） |
| `Forms/LoginForm.cs` | WebView2 内嵌登录窗口，读取登录 token |
| `Api/TraeApiClient.cs` | Trae 云 API 客户端（状态 / 签到 / 积分） |
| `Api/GitHubApiClient.cs` | GitHub 设备码授权与云端部署 API 客户端 |
| `Config/AppConfig.cs` | 本地配置的加载与保存 |
| `Services/AutoStartManager.cs` | 开机自启动（注册表 Run 键） |
| `Services/FeishuNotifier.cs` | 飞书机器人推送（签到结果通知） |
| `Services/GitHubSecret.cs` | GitHub Actions secret 加密（libsodium） |
| `Services/TokenUtils.cs` | 登录 token 判定（避免误读失效 token） |
| `Controls/HistoryChart.cs` | 总积分趋势折线图控件 |

---

## 签到原理

Trae 的每日签到本质是调用官方云 API。`TraeApiClient` 封装了三个接口（`BaseUrl = https://api.trae.cn`）：

| 接口 | 说明 |
|------|------|
| `POST /trae/api/v2/ug/checkin_credits/status` | 查询今日签到状态与单日奖励 |
| `POST /trae/api/v2/ug/checkin_credits/claim` | 执行每日签到 |
| `POST /trae/api/v2/pay/user_current_entitlement_list` | 查询剩余积分 |

请求需要携带认证头：

```
Authorization: Cloud-IDE-JWT <token>
x-device-id: <设备号>
```

其中 **token** 是登录后在浏览器 `localStorage` 中存储的 `Cloud-IDE-Token`（JWT）。程序通过内嵌 WebView2 登录页面获取它，并持久化保存，之后每次请求自动带上。

**自动签到逻辑**（`MainForm.CheckAutoCheckinAsync`）：

1. 每 10 秒触发一次检查。
2. 若当天已执行过自动签到则跳过。
3. 读取用户设定的签到时间（如 `08:00`）。
4. 当前时间晚于设定时间且当天未签 → 执行签到。
5. 若程序在设定时间之后才启动，则自动**补签**一次，保证当天不遗漏。

---

## 使用说明

### 运行环境

- Windows 10 / 11
- [.NET 9 运行时](https://dotnet.microsoft.com/download)（或直接使用已发布的可执行文件）
- [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)（Win10/11 一般自带）

### 首次使用

1. 启动程序。
2. 首次会弹出登录窗口，用手机号 + 验证码登录 Trae。
3. 登录成功后自动识别 token 并进入主界面。
4. 在「仪表盘」或「设置」页设置自动签到时间（默认 `08:00`）。

### 构建

```bash
# 1. 编译主程序（框架依赖，输出到统一产物目录）
dotnet build TraeCheckin.csproj -c Release

# 2. 发布独立启动器（自包含单文件，输出到同一目录）
dotnet publish TraeCheckin.Launcher\TraeCheckin.Launcher.csproj -c Release
```

主程序与启动器的构建产物统一输出到 `TraeCheckin开发\` 目录，主要文件：

| 文件 | 说明 |
|------|------|
| `TraeCheckin.exe` | 主程序（需 .NET 9 桌面运行时） |
| `TraeCheckin.Launcher.exe` | 独立启动器（自包含，自动检测/补全依赖） |

日常使用建议双击 `TraeCheckin.Launcher.exe`，它会自动检查 .NET 9 与 WebView2 运行时，缺失时自动补全，再拉起主程序。

---

## 云端签到部署（GitHub Actions）

除本机自动签到外，程序还支持把签到脚本部署到你的 GitHub 仓库，由 GitHub Actions 每天定时自动签到，**无需本机 24 小时挂机**。

### 部署流程

1. 在「云端签到」页点击「授权 GitHub」，走 **OAuth 设备码授权**拿到 access_token。
2. 再点「一键部署到云端」，程序自动完成：
   - fork 源仓库（若你已是源仓库 owner 则自动跳过）；
   - 写入 `TRAE_SESSION` 与 `TRAE_DEVICE_ID` 两个 Actions secret（若已在设置页配置飞书推送，还会写入 `FEISHU_WEBHOOK`）；
   - 启用定时 workflow；
   - 触发一次验证运行并等待结果。
3. 部署成功后，GitHub 每天 **北京时间 8:00**（cron `0 0 * * *`）自动执行签到。

云端脚本 [checkin.py](checkin.py) 用 `X-Cloudide-Session` Cookie 换取全新 JWT 后执行签到，workflow 定义见 [checkin.yml](.github/workflows/checkin.yml)。

### 注意事项

- 云端签到的凭证是 `TRAE_SESSION`（约 **14 天**有效）。过期后需回到本程序重新登录 Trae，再点一次「一键部署到云端」刷新 secret。
- 首次部署需要 GitHub OAuth 授权；授权信息（access_token 与用户名）保存在本地配置中，不会写入云端仓库。

---

## WorkBuddy 自动签到（GitHub Actions）

Trae 之外，本仓库还附带一个独立的 WorkBuddy 每日签到脚本 [checkin_workbuddy.py](checkin_workbuddy.py)，同样跑在 GitHub Actions 上，与 Trae 的 workflow **相互独立、互不影响**（一个失败不会拖累另一个）。

机制差别：Trae 靠 `X-Cloudide-Session` Cookie 换取 JWT；WorkBuddy 直接使用桌面端落盘的**长效 accessToken**（约 60 天），所以维护频率更低。

### 它是怎么工作的

```
POST https://<域名>/v2/billing/meter/checkin-activity-status   查询今日签到状态
POST https://<域名>/v2/billing/meter/daily-checkin             执行签到
     Header: Authorization: Bearer <accessToken>
             X-User-Id: <uid>
     Body:   {}
```

响应语义：

| 返回 | 含义 | 脚本判定 |
|---|---|---|
| `code = 0` | 签到成功 | ✅ 成功 |
| `code = 10001` | 今天已签到（幂等） | ✅ 正常，不会让 job 失败 |
| `HTTP 401` | 登录态过期 | ❌ 需刷新令牌 |

域名默认 `copilot.tencent.com`，可用 `WORKBUDDY_DOMAIN` 覆盖。

### 需要配置的 Secrets

| Secret 名称 | 必填 | 说明 |
|---|---|---|
| `WORKBUDDY_TOKEN` | ✅ | 桌面端登录态里的 `auth.accessToken`（约 60 天有效） |
| `WORKBUDDY_UID` | ⬜ | 桌面端登录态里的 `account.uid`，作为 `X-User-Id` 发送 |
| `WORKBUDDY_DOMAIN` | ⬜ | 接口域名，缺省 `copilot.tencent.com` |
| `WORKBUDDY_TOKEN_2` / `WORKBUDDY_UID_2` | ⬜ | 第 2 个账号，依次类推 |
| `FEISHU_WEBHOOK` | ⬜ | 与 Trae 共用；签到后推一条汇总 |

### 怎么拿到这些值

不用手动翻文件，直接用仓库自带的提取脚本（默认只显示脱敏信息，**不会完整打印令牌**）：

```powershell
# 查看脱敏概览：令牌长度、到期时间、uid、域名
powershell -ExecutionPolicy Bypass -File tools\workbuddy-auth.ps1

# 把 WORKBUDDY_TOKEN 的值复制到剪贴板，直接粘贴进 Secrets
powershell -ExecutionPolicy Bypass -File tools\workbuddy-auth.ps1 -CopyToken
```

它读取的是 WorkBuddy 桌面端落盘的登录态文件：

- Windows：`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`
- macOS：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`

> ⚠️ 该文件里的 `accessToken` **等同于登录密码**，只能放进 Secrets。不要提交到仓库、不要贴到聊天记录或文章里，也不要用「只露前几位」的方式打码——尾部字符同样是真实内容。

### 本地先试跑一次

不配任何环境变量，直接复用本机登录态：

```bash
python checkin_workbuddy.py --from-local --status-only   # 只查状态，不签到
python checkin_workbuddy.py --from-local                 # 真实签到
```

### 在 GitHub 上启用

1. 把本仓库 fork / push 到自己的 GitHub 仓库，保留默认分支。
2. 进入 **Actions** 标签页，启用 workflows。
3. 左侧选中 **WorkBuddy Daily Checkin**，若显示 **Enable workflow** 就点一下（公开仓库 fork 后 scheduled workflow 默认被禁用）。
4. Settings → Secrets and variables → Actions，添加 `WORKBUDDY_TOKEN`（需要的话再加 `WORKBUDDY_UID`）。
5. Actions → **Run workflow** 手动跑一次，日志出现 `本次积分=100` 或 `今天已签到，请明天再来（正常）` 即为成功。
6. 之后每天 **北京时间 08:00**（cron `0 0 * * *`）自动执行。

`workflow_dispatch` 已配置，随时可手动触发验证，无需等定时。

### 注意事项

- 令牌约 **60 天**失效。只要你正常使用 WorkBuddy 桌面端，登录态会自动刷新；若长期不开客户端导致过期，日志会报 `HTTP 401`，重开一次客户端后用提取脚本刷新 Secret 即可。
- 全程纯 HTTP 调用，**不需要模拟点击、不要求客户端开着**，脚本仅依赖标准库。
- 若出现「本机能跑通、Actions 里报 401」的情况，通常是 GitHub 机房 IP 被风控拦截，可改用自托管 runner，或用本机定时任务运行同一脚本。

---

## 签到结果推送（飞书）

可在「设置」页粘贴飞书自定义机器人的 webhook 地址，签到成功/失败后主动推送到飞书群：

1. 在飞书群中添加「自定义机器人」，复制它的 webhook 地址。
2. 在本程序「设置」页粘贴到「签到结果推送」输入框，点「保存」，再点「测试推送」验证。
3. 部署云端时若已配置 webhook，会一并写入 `FEISHU_WEBHOOK` secret，云端签到同样会推送。

> 注意：飞书机器人安全设置建议选「自定义关键词」或关闭「签名校验」；本程序当前实现的是不带签名的文本消息推送。

---

## 配置文件位置

| 内容 | 路径 |
|------|------|
| 配置（token、Session、GitHub 授权、飞书 webhook、自动签到设置） | `%APPDATA%\TraeCheckin\config.json` |
| 签到历史 | `%APPDATA%\TraeCheckin\history.txt` |
| 总积分趋势数据 | `%APPDATA%\TraeCheckin\credits_total.txt` |
| WebView2 用户数据 | `%LOCALAPPDATA%\TraeCheckin\WebView` |

> ⚠️ **安全提示**：`config.json` 中保存着你的登录 token 与 GitHub 授权信息。请勿将本项目中的 `config.json` 提交到任何公开仓库，或分享给他人。

---

## 使用声明

本项目为作者个人技术学习成果，旨在研究 Windows 桌面应用开发及云 API 调用技术。

**使用前提：**
- 使用本工具前，请确保您已阅读并同意 Trae 官方服务条款。
- 本工具仅作为**个人日常使用的辅助提醒**，在您本人拥有的设备上运行，**不能替代您对平台规则的遵守**。
- 签到积分及相关权益归 Trae 平台所有，本工具仅调用平台公开的云端接口完成状态查询与签到操作，**不修改、不拦截、不篡改任何平台数据**。

**明确禁止：**
- 禁止将本工具用于批量注册、批量签到、积分倒卖、刷量或任何可能影响平台正常运营的行为。
- 禁止将本工具用于非本人拥有的账号，或用于共享账号、租赁账号等场景。
- 禁止在二次分发本工具时移除或修改本声明。

**数据安全：**
- 您的登录凭证（token）仅保存在本地配置文件（`%APPDATA%\TraeCheckin\config.json`）中，不会上传至作者或任何第三方服务器。
- 如您使用「云端签到」功能，凭证将仅存储于**您个人 GitHub 仓库的 Secrets** 中，由 GitHub Actions 执行。
- 请勿将包含 token 的配置文件提交至公开仓库或分享给他人。

**责任限制：**
- 本工具按"现状"提供，作者不对因使用本工具导致的账号限制、积分清零、功能调整或其他平台处罚承担责任。
- 如 Trae 官方推出官方自动签到或同类功能，建议立即停用本工具并转用官方方案。

**与官方关系：**
- 本项目为独立开源作品，与字节跳动、Trae 或其关联公司**无任何隶属、合作或授权关系**。

---

## License

[GPL-3.0](LICENSE)

© 星梦
