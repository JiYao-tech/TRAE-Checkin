#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 每日签到脚本（GitHub Actions 版）

原理：
  WorkBuddy 桌面端登录后会把登录态以明文 JSON 落盘，其中 `auth.accessToken` 是
  长效访问令牌（约 60 天有效），`auth.domain` 记录当前使用的接口域名。
  带上该令牌直接调官方签到接口即可完成每日签到，无需打开客户端、无需模拟点击。

  与 Trae 的差别：Trae 靠 Cookie 换 JWT；WorkBuddy 直接用一个长效 Bearer 令牌。
  两者都以 GitHub Actions Secrets 注入，互不影响。

环境变量：
  WORKBUDDY_TOKEN     账号 1 的 accessToken（必填）
  WORKBUDDY_UID       账号 1 的 uid，作为 X-User-Id 发送（选填，建议填）
  WORKBUDDY_DOMAIN    接口域名（选填，缺省 copilot.tencent.com）
  WORKBUDDY_TOKEN_N   第 N(N≥2) 个账号的 accessToken；缺失即停止读取更多账号
  WORKBUDDY_UID_N     第 N 个账号的 uid（选填）
  FEISHU_WEBHOOK      选填，全部账号签到后推送一条汇总

本地自测（无需手填环境变量，直接读本机登录态）：
  python checkin_workbuddy.py --from-local
  python checkin_workbuddy.py --from-local --status-only   # 只查状态不签到

依赖：仅标准库。
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_DOMAIN = "copilot.tencent.com"
STATUS_PATH = "/v2/billing/meter/checkin-activity-status"
CLAIM_PATH = "/v2/billing/meter/daily-checkin"

LOCAL_INFO_PATHS = [
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "CodeBuddyExtension", "Data", "Public", "auth", "workbuddy-desktop.info",
    ),
    os.path.expanduser(
        "~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info"
    ),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _post(url, headers, body="{}"):
    """POST 请求。非 2xx 不抛异常，返回 (status, text) 供上层判断。"""
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, "请求异常: %s" % e


def build_headers(token, uid, domain, token_type="Bearer"):
    base = "https://" + domain
    headers = {
        "Authorization": "%s %s" % (token_type or "Bearer", token),
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Referer": base + "/",
        "Origin": base,
    }
    if uid:
        headers["X-User-Id"] = uid
    return headers


def _json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def call(domain, path, token, uid, token_type, label):
    """调一次接口并归一化结果。始终返回三元组 (ok, 描述, 原始 data)。"""
    status, text = _post("https://%s%s" % (domain, path), build_headers(token, uid, domain, token_type))
    data = _json(text)

    if status in (401, 403):
        return False, ("登录态失效(HTTP %d)：accessToken 可能已过期，"
                       "请重新登录 WorkBuddy 后更新 WORKBUDDY_TOKEN" % status), data

    code = None
    msg = ""
    if isinstance(data, dict):
        code = data.get("code", data.get("Code"))
        msg = data.get("msg") or data.get("message") or ""

    # 先看业务 code：接口可能用非 200 的 HTTP 状态表示"今天已签到"，不能只看状态码
    if code == 0:
        return True, msg or "成功", data
    if code == 10001:
        # 已签到属于幂等正常返回，不算失败
        return True, "今天已签到，请明天再来（正常）", data
    if code is None:
        if status == 200:
            return True, msg or "成功（响应无 code 字段）", data
        return False, "%s 失败：HTTP %d %s" % (label, status, text[:200]), data
    return False, "失败：HTTP %d code=%s %s" % (status, code, msg), data


def describe(data):
    """从响应里挑出连续天数、积分等可读信息。"""
    if not isinstance(data, dict):
        return ""
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    parts = []
    mapping = (
        ("credits", "本次积分"), ("credit", "本次积分"), ("points", "本次积分"),
        ("continuousDays", "连续天数"), ("continuous_days", "连续天数"), ("streak", "连续天数"),
        ("totalDays", "累计签到"), ("totalCheckinDays", "累计签到"),
    )
    for key, label in mapping:
        v = inner.get(key)
        if v is None:
            continue
        if any(label in p for p in parts):
            continue
        parts.append("%s=%s" % (label, v))
    return "，".join(parts)


def load_local_account():
    """读取本机 WorkBuddy 登录态文件。绝不打印令牌内容。"""
    for path in LOCAL_INFO_PATHS:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                info = json.load(f)
        except Exception as e:
            print("读取登录态失败：%s（%s）" % (path, e))
            continue
        auth = info.get("auth") or {}
        acct = info.get("account") or {}
        token = (auth.get("accessToken") or "").strip()
        if not token:
            continue
        return {
            "token": token,
            "uid": (acct.get("uid") or "").strip(),
            "domain": (auth.get("domain") or "").strip() or DEFAULT_DOMAIN,
            "token_type": (auth.get("tokenType") or "Bearer").strip(),
            "expires_at": auth.get("expiresAt"),
            "nickname": acct.get("nickname") or "",
            "path": path,
        }
    return None


def warn_expiry(expires_at):
    """令牌到期提醒（expiresAt 为毫秒时间戳）。"""
    if not expires_at:
        return
    try:
        ts = float(expires_at)
        if ts > 1e11:          # 毫秒
            ts /= 1000.0
        exp = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    except Exception:
        return
    left = exp - datetime.datetime.now(datetime.timezone.utc)
    days = left.days
    if days < 0:
        print("提示：登录态已过期（%s UTC），接口大概率会返回 401。" % exp.strftime("%Y-%m-%d %H:%M"))
    elif days < 7:
        print("提示：登录态将在 %d 天后过期（%s UTC），建议尽快重新登录 WorkBuddy 刷新令牌。"
              % (days, exp.strftime("%Y-%m-%d %H:%M")))


def iter_accounts():
    """产出 (序号, token, uid, domain, token_type)。账号 1 读 WORKBUDDY_TOKEN，
    之后依次读 WORKBUDDY_TOKEN_2、_3… 直到缺空为止。"""
    domain = (os.environ.get("WORKBUDDY_DOMAIN") or "").strip() or DEFAULT_DOMAIN
    token = (os.environ.get("WORKBUDDY_TOKEN") or "").strip()
    if token:
        yield 1, token, (os.environ.get("WORKBUDDY_UID") or "").strip(), domain, "Bearer"
    n = 2
    while True:
        token = (os.environ.get("WORKBUDDY_TOKEN_%d" % n) or "").strip()
        if not token:
            break
        yield n, token, (os.environ.get("WORKBUDDY_UID_%d" % n) or "").strip(), domain, "Bearer"
        n += 1


def notify_feishu(webhook, text):
    """向飞书机器人推送一条文本消息；webhook 为空则跳过。"""
    if not webhook:
        return None
    try:
        payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
        req = urllib.request.Request(
            webhook, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception:
        return None


def beijing_now_str():
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def main():
    from_local = "--from-local" in sys.argv
    status_only = "--status-only" in sys.argv

    accounts = []
    if from_local:
        local = load_local_account()
        if not local:
            print("错误：未找到本机 WorkBuddy 登录态文件。请先登录 WorkBuddy 桌面端。")
            print("查找路径：")
            for p in LOCAL_INFO_PATHS:
                if p:
                    print("  " + p)
            sys.exit(1)
        print("已读取本机登录态：%s" % local["path"])
        print("账号昵称：%s" % (local["nickname"] or "(未知)"))
        print("接口域名：%s" % local["domain"])
        warn_expiry(local.get("expires_at"))
        accounts.append((1, local["token"], local["uid"], local["domain"], local["token_type"]))
    else:
        accounts = list(iter_accounts())
        if not accounts:
            print("错误：缺少环境变量 WORKBUDDY_TOKEN")
            sys.exit(1)

    webhook = (os.environ.get("FEISHU_WEBHOOK") or "").strip()
    ok_names, fail_names = [], []
    all_ok = True

    for index, token, uid, domain, token_type in accounts:
        name = "账号 %d" % index
        print("[%s] 域名=%s uid=%s" % (name, domain, uid[:8] + "…" if len(uid) > 10 else uid))

        if status_only:
            ok, desc, data = call(domain, STATUS_PATH, token, uid, token_type, "查询状态")
            print("[%s] %s %s" % (name, "状态正常：" if ok else "状态异常：", desc))
            detail = describe(data)
            if detail:
                print("[%s] %s" % (name, detail))
            (ok_names if ok else fail_names).append(name)
            if not ok:
                all_ok = False
            continue

        ok, desc, data = call(domain, CLAIM_PATH, token, uid, token_type, "签到")
        if ok:
            print("[%s] %s" % (name, desc))
            detail = describe(data)
            if detail:
                print("[%s] %s" % (name, detail))
            ok_names.append(name)
        else:
            print("[%s] 签到失败：%s" % (name, desc))
            fail_names.append(name)
            all_ok = False

    summary = ["WorkBuddy 每日签到结果", "时间：%s" % beijing_now_str()]
    if ok_names:
        summary.append("成功：" + "、".join(ok_names))
    if fail_names:
        summary.append("失败：" + "、".join(fail_names))
    if webhook and (ok_names or fail_names):
        notify_feishu(webhook, "\n".join(summary))

    if not all_ok:
        sys.exit(1)
    print("全部账号签到完成")


if __name__ == "__main__":
    main()
