# 深澜校园网自动登录（srun Portal）

在 Linux 上自动登录「深澜（srun）」认证系统校园网的脚本，开机后无需打开浏览器手动登录。

本仓库提供两种实现，按你学校门户的类型选择：

| 方案 | 文件 | 适用场景 |
| --- | --- | --- |
| 浏览器自动化（推荐） | `srun_login.js` | 深澜「无线-v2」门户，纯 HTTP 请求无法触发网关强制跳转、拿不到 `wlanuserip`/`mac` 参数时 |
| 通用 RSA 加密 | `srun_login.py` | 标准 srun 门户，未认证时网关会把外网 HTTP 请求 302 到 `index.jsp?<queryString>` |

> 实测：河海大学 `eportal.hhu.edu.cn`（无线-v2）用浏览器方案可直接登录；通用 RSA 方案因拿不到重定向查询串而无法登录。

## 方案一：浏览器自动化（`srun_login.js`）

原理：驱动本机 Chrome 无头模式，让浏览器完整走一遍「访问外网 → 网关重定向到登录页 → 填账号密码 → 认证」，因此不依赖对网关跳转逻辑的手工复现，最稳妥。

### 前置条件

- 已安装 Chrome；
- 已安装 Node.js；
- 已连接校园网 Wi-Fi（未认证状态）。

### 安装

```bash
mkdir -p ~/.local/share/srun-campus-login
cp srun_login.js ~/.local/share/srun-campus-login/
cd ~/.local/share/srun-campus-login
npm install puppeteer-core
```

### 配置

```bash
mkdir -p ~/.config/srun-login
cp config.example ~/.config/srun-login/config
```

编辑 `~/.config/srun-login/config`，填入：

```ini
USERNAME=你的学号或工号
PASSWORD=你的校园网密码
```

然后收紧权限：

```bash
chmod 600 ~/.config/srun-login/config
```

也可以用环境变量 `SRUN_USER` / `SRUN_PASS`。Chrome 路径不是 `/usr/bin/google-chrome` 时，用 `SRUN_CHROME` 覆盖。

### 手动运行

```bash
node ~/.local/share/srun-campus-login/srun_login.js
```

- 已在线时打印「已在线（已认证），无需登录」并退出；
- 未认证时自动登录，成功后打印「登录成功」。

## 方案二：通用 RSA 加密（`srun_login.py`）

纯 Python 标准库实现，复现了门户 `login_bch.js` 的 RSA 加密流程（密码 + `>` + mac，反转后 RSA 加密）。适用于网关会正常把 HTTP 请求重定向到 `index.jsp?<queryString>` 的标准门户。

### 通用 Python 方案配置

复制 `config.example` 为 `~/.config/srun-login/config`，填入：

```ini
PORTAL_HOST=http://eportal.example.edu.cn
USERNAME=你的学号或工号
PASSWORD=你的校园网密码
```

未认证时用浏览器访问任意外网 HTTP 地址，被重定向到的登录页域名即 `PORTAL_HOST`。

## 配置开机自启

仓库提供 systemd 用户服务 + 定时器（开机 20 秒后运行一次，之后每 60 秒检测一次；已在线自动跳过）。

```bash
mkdir -p ~/.config/systemd/user
cp srun-login.service ~/.config/systemd/user/
cp srun-login.timer ~/.config/systemd/user/
```

修改 `~/.config/systemd/user/srun-login.service` 里的 `ExecStart` 路径，把 `YOUR_USERNAME` 和脚本路径改成你实际的。

```bash
systemctl --user daemon-reload
systemctl --user enable --now srun-login.timer
```

若希望未登录图形会话时也能后台运行（重启后自动登录），开启 linger：

```bash
sudo loginctl enable-linger "$USER"
```

## 排查

```bash
systemctl --user status srun-login.timer --no-pager
journalctl --user -u srun-login.service -n 20 --no-pager
```

## 免责声明

本项目仅用于学习与个人便利，请遵守所在学校/园区的网络使用规定，在你自己有权使用的账号与设备上运行。
