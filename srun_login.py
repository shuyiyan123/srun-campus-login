#!/usr/bin/env python3
"""深澜 srun Portal 校园网自动登录脚本（通用版）。

适用于使用「深澜 srun」认证系统的校园网，登录流程与浏览器端
login_bch.js / AuthInterFace.js 完全一致：

1. 未认证时访问外网 HTTP，网关会 302 到 index.jsp?<queryString>；
2. 用 queryString 调 pageInfo 接口拿 RSA 公钥与 passwordEncrypt 开关；
3. 密码按 ``password + ">" + mac`` 拼接、反转后做 RSA 加密；
4. POST login 完成认证。

使用前请先复制 ``config.example`` 为 ``~/.config/srun-login/config`` 并填写
你自己的门户地址、用户名和密码。详见 README.md。
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import ssl

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 触发重定向的外网探测地址（纯 HTTP，未认证时会被网关 302 到门户）
TRIGGER_URLS = [
    "http://www.baidu.com/",
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://fedoraproject.org/static/hotspot.txt",
]

CONFIG_PATH = os.path.expanduser("~/.config/srun-login/config")


def load_config():
    """读取配置文件，并允许用环境变量覆盖。"""
    values = {
        "PORTAL_HOST": os.environ.get("SRUN_PORTAL_HOST", ""),
        "USERNAME": os.environ.get("SRUN_USER", ""),
        "PASSWORD": os.environ.get("SRUN_PASS", ""),
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().upper()
                value = value.strip()
                if key in values and not values[key]:
                    values[key] = value
    return values


def _opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # 禁用代理，直连校园网
    proxy = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(proxy, urllib.request.HTTPSHandler(context=ctx))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _no_redirect_opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    proxy = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(proxy, NoRedirect, urllib.request.HTTPSHandler(context=ctx))


def get(url, headers=None, timeout=8, no_redirect=False):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    op = _no_redirect_opener() if no_redirect else _opener()
    try:
        return op.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return e


def post_form(url, data, headers=None, timeout=8):
    body = urllib.parse.urlencode(data).encode("utf-8")
    h = headers or {}
    h.setdefault("User-Agent", UA)
    h.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    return _opener().open(req, timeout=timeout)


def enc(s):
    """等价于 JS 的 encodeURIComponent。"""
    return urllib.parse.quote(s, safe="-_.!~*'()")


def rsa_encrypt(message: str, e_hex: str, n_hex: str) -> str:
    """复现 security.js 中 RSAUtils.encryptedString 的结果。"""
    rev = message[::-1]
    m = int.from_bytes(rev.encode("latin-1"), "little")
    e = int(e_hex, 16)
    n = int(n_hex, 16)
    c = pow(m, e, n)
    h = format(c, "x")
    if len(h) % 4:
        h = h.zfill(len(h) + (4 - len(h) % 4))
    return h


def portal_url(host):
    host = host.rstrip("/")
    return host + "/eportal/"


def get_query_string(host):
    """未认证时，访问外网 HTTP 会被网关 302 到 index.jsp?queryString。"""
    for probe in TRIGGER_URLS:
        try:
            r = get(probe, no_redirect=True)
            if r.code in (301, 302, 303, 307):
                loc = r.headers.get("Location", "")
                if "index.jsp" in loc or "eportal" in loc:
                    parsed = urllib.parse.urlparse(loc)
                    qs = urllib.parse.unquote(parsed.query)
                    if qs and "mac=" in qs:
                        return qs
        except Exception:
            continue
    # 兜底：直接访问门户根路径，未认证时门户也可能 302 到 index.jsp
    try:
        r = get(host, no_redirect=True)
        if r.code in (301, 302, 303, 307):
            loc = r.headers.get("Location", "")
            if "index.jsp" in loc:
                parsed = urllib.parse.urlparse(loc)
                qs = urllib.parse.unquote(parsed.query)
                if qs:
                    return qs
    except Exception:
        pass
    return None


def extract_param(query_string, name):
    for part in query_string.split("&"):
        if part.startswith(name + "="):
            return part[len(name) + 1:]
    return ""


def main():
    cfg = load_config()
    host = cfg["PORTAL_HOST"]
    username = cfg["USERNAME"]
    password = cfg["PASSWORD"]

    if not host:
        print("ERROR: 未设置门户地址（PORTAL_HOST）", file=sys.stderr)
        return 1
    if not username or not password:
        print("ERROR: 未设置用户名或密码", file=sys.stderr)
        return 1

    portal = portal_url(host)
    qs = get_query_string(host)
    if not qs:
        print("已联网或未捕获到重定向查询串", file=sys.stderr)
        return 0

    mac = extract_param(qs, "mac") or "111111111"

    # 1) pageInfo 拿公钥与加密开关
    raw = post_form(portal + "InterFace.do?method=pageInfo",
                    {"queryString": enc(qs)}).read().decode("utf-8", "replace")
    info = json.loads(raw)
    encrypt_flag = str(info.get("passwordEncrypt", "false")).lower() == "true"
    e_hex = info.get("publicKeyExponent", "10001")
    n_hex = info.get("publicKeyModulus", "")

    # 2) 密码处理（与 login_bch.js 一致）
    pwd = password
    flag = "false"
    if encrypt_flag and n_hex:
        pwd = rsa_encrypt(password + ">" + mac, e_hex, n_hex)
        flag = "true"

    # 3) login
    data = {
        "userId": enc(enc(username)),
        "password": enc(enc(pwd)),
        "service": "",
        "queryString": enc(enc(qs)),
        "operatorPwd": "",
        "operatorUserId": "",
        "validcode": "",
        "passwordEncrypt": enc(enc(flag)),
    }
    resp = post_form(portal + "InterFace.do?method=login", data)
    result = json.loads(resp.read().decode("utf-8", "replace"))
    print(json.dumps(result, ensure_ascii=False))
    if result.get("result") == "success":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
