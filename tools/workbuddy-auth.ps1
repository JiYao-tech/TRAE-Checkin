<#
.SYNOPSIS
    从本机 WorkBuddy 登录态中提取填入 GitHub Secrets 所需的值。

.DESCRIPTION
    读取 WorkBuddy 桌面端落盘的登录态文件，输出配置 Actions Secrets 需要的内容。
    默认只显示脱敏信息；加 -CopyToken / -CopyUid 可直接复制到剪贴板。
    本脚本不会完整打印令牌内容，也不会把令牌写入任何文件。

    登录态文件位置：
      Windows  %LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info
      macOS    ~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\workbuddy-auth.ps1
    查看脱敏概览（令牌长度、到期时间、uid、域名）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\workbuddy-auth.ps1 -CopyToken
    把 WORKBUDDY_TOKEN 的值复制到剪贴板，直接粘贴进 GitHub Secrets。
#>
[CmdletBinding()]
param(
    [switch]$CopyToken,
    [switch]$CopyUid
)

$ErrorActionPreference = 'Stop'

$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info'),
    (Join-Path $env:APPDATA 'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info')
)

$path = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $path) {
    Write-Host '未找到 WorkBuddy 登录态文件。请先登录 WorkBuddy 桌面端，再运行本脚本。'
    Write-Host '已查找以下路径：'
    $candidates | ForEach-Object { Write-Host "  $_" }
    exit 1
}

$info = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
$auth = $info.auth
$acct = $info.account

$token   = if ($auth.accessToken) { $auth.accessToken.Trim() } else { '' }
$uid     = if ($acct.uid)         { $acct.uid.Trim() }         else { '' }
$domain  = if ($auth.domain)      { $auth.domain.Trim() }      else { '' }
$expires = $auth.expiresAt

if (-not $token) {
    Write-Host '登录态文件里没有 accessToken，请重新登录 WorkBuddy 桌面端后再试。'
    exit 1
}

function Get-Masked {
    param([string]$Value, [int]$Head = 6, [int]$Tail = 4)
    if ([string]::IsNullOrEmpty($Value)) { return '(空)' }
    if ($Value.Length -le ($Head + $Tail)) { return ('*' * $Value.Length) }
    return $Value.Substring(0, $Head) + ('*' * 8) + $Value.Substring($Value.Length - $Tail)
}

$expText = '未知'
if ($expires) {
    $ts = [double]$expires
    if ($ts -gt 1e11) { $ts = $ts / 1000 }
    $exp = [DateTimeOffset]::FromUnixTimeSeconds([long]$ts).ToLocalTime()
    $days = [math]::Round(($exp - [DateTimeOffset]::Now).TotalDays, 1)
    $expText = "{0}（约 {1} 天后）" -f $exp.ToString('yyyy-MM-dd HH:mm'), $days
}

Write-Host ''
Write-Host "登录态文件：$path"
Write-Host "账号昵称  ：$($acct.nickname)"
Write-Host ''
Write-Host '需要写入 GitHub Secrets 的值：'
Write-Host ("  WORKBUDDY_TOKEN  = {0}  （共 {1} 字符）" -f (Get-Masked $token), $token.Length)
Write-Host ("  WORKBUDDY_UID    = {0}" -f $uid)
Write-Host ("  WORKBUDDY_DOMAIN = {0}   （与默认值一致时可不配）" -f $domain)
Write-Host ''
Write-Host "令牌到期  ：$expText"
Write-Host '提示      ：只要你还正常使用 WorkBuddy 桌面端，登录态会自动刷新；'
Write-Host '            若超过 60 天完全不开客户端，令牌会过期，届时重开一次客户端即可。'
Write-Host ''

if ($CopyToken) {
    Set-Clipboard -Value $token
    Write-Host 'WORKBUDDY_TOKEN 已复制到剪贴板，可直接粘贴到 GitHub Secrets。'
}
if ($CopyUid) {
    Set-Clipboard -Value $uid
    Write-Host 'WORKBUDDY_UID 已复制到剪贴板。'
}
if (-not $CopyToken -and -not $CopyUid) {
    Write-Host '提示：加 -CopyToken 可直接复制令牌到剪贴板（脚本不会完整打印令牌内容）。'
}
