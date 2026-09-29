# 深澜校园网自动登录脚本（srun Portal）

一个在 Linux 上自动登录「深澜（srun）」认证系统校园网的脚本。开机后无需打开浏览器、手动输入账号密码，脚本会自动完成 Portal 认证并保持在线。

> 适用场景：学校/园区使用深澜 srun 认证系统，连上 Wi-Fi 后需要弹出门户页面登录才能上网。

## 目录

- [原理](#原理)
- [前置条件](#前置条件)
- [安装](#安装)
- [配置](#配置)
- [配置开机自启](#配置开机自启)
- [验证与排查](#验证与排查)
- [常见问题](#常见问题)
- [免责声明](#免责声明)

## 原理

这类校园网的认证流程通常是这样：

1. 设备连上 Wi-Fi，拿到一个内网地址，但此时还不能访问外网；
2. 网关（AC）把所有 HTTP 请求重定向到登录门户 `eportal.<学校域名>`；
3. 登录页通过 `pageInfo` 接口返回 RSA 公钥；
4. 浏览器把密码按 `密码 + ">" + mac` 拼接、**反转**后做 **RSA 加密**，再提交给 `login` 接口；
5. 认证成功后即可正常上网。

其中第 4 步的加密逻辑比较关键：它不是简单把密码发出去，而是先拼上一个从重定向 URL 里取出的 `mac` 参数，再把整个字符串反转，最后用 RSA 公钥加密。这也是本脚本要复现的核心。

### 关键接口

| 接口 | 方法 | 作用 |
| --- | --- | --- |
| `/eportal/InterFace.do?method=pageInfo` | POST | 返回 RSA 公钥（`publicKeyExponent`、`publicKeyModulus`）以及是否启用密码加密（`passwordEncrypt`） |
| `/eportal/InterFace.do?method=login` | POST | 提交用户名、加密后的密码完成认证 |
| `/eportal/InterFace.do?method=logout` | POST | 下线 |
| `/eportal/InterFace.do?method=keepalive` | POST | 心跳保活（部分学校需要） |

## 前置条件

- Linux 系统（本脚本不依赖任何第三方库，仅用 Python 3 标准库）；
- 已连接校园网 Wi-Fi；
- 知道自己的认证门户地址、用户名和密码。

## 安装

把脚本复制到用户目录的 `bin` 下，并添加执行权限：

```bash
install -m 0755 srun_login.py ~/.local/bin/srun-login.py
```

确保 `~/.local/bin` 在你的 `PATH` 里（大多数发行版默认包含）。若没有，可在 `~/.bashrc` 或 `~/.zshrc` 中追加：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 配置

创建配置目录，并从模板生成配置文件：

```bash
mkdir -p ~/.config/srun-login
cp config.example ~/.config/srun-login/config
```

编辑配置文件，填入你的信息：

```ini
PORTAL_HOST=http://eportal.example.edu.cn
USERNAME=你的学号或工号
PASSWORD=你的校园网密码
```

然后收紧配置文件权限，避免密码被其他用户读取：

```bash
chmod 600 ~/.config/srun-login/config
```

> 也可以不写配置文件，改用环境变量：
>
> ```bash
> SRUN_PORTAL_HOST=http://eportal.example.edu.cn \
> SRUN_USER=你的学号 \
> SRUN_PASS=你的密码 \
> ~/.local/bin/srun-login.py
> ```

### 如何找到门户地址

未认证状态下（比如刚开机、尚未登录时），用浏览器访问任意外网站点，会被自动重定向到登录页，地址栏里那个域名就是门户地址，例如：

```text
http://eportal.xxx.edu.cn/eportal/index.jsp?wlanuserip=...
```

取 `http://eportal.xxx.edu.cn` 填入 `PORTAL_HOST` 即可。

## 配置开机自启

本仓库提供了 systemd 用户服务 + 定时器的写法。定时器在开机 20 秒后运行一次，之后每 60 秒检查一次；已联网时脚本会直接跳过，未联网时才登录。

1. 把 service/timer 文件复制到用户 systemd 目录：

```bash
mkdir -p ~/.config/systemd/user
cp srun-login.service ~/.config/systemd/user/
cp srun-login.timer ~/.config/systemd/user/
```

2. 修改 service 文件里的 `ExecStart` 路径，把 `YOUR_USERNAME` 换成你的用户名，使其指向你实际安装的脚本路径。

3. 启用并启动定时器：

```bash
systemctl --user daemon-reload
systemctl --user enable --now srun-login.timer
```

4. 若希望「未登录桌面会话时也能在后台运行」（例如重启后没马上登录图形界面），开启 linger：

```bash
sudo loginctl enable-linger "$USER"
```

## 验证与排查

手动运行一次：

```bash
~/.local/bin/srun-login.py
```

- 如果已联网，会打印「已联网或未捕获到重定向查询串」并以 0 退出，这是正常现象；
- 如果未联网，会打印 `login` 接口返回的 JSON，`"result": "success"` 即登录成功。

查看定时器/服务的状态与最近日志：

```bash
systemctl --user status srun-login.timer --no-pager
systemctl --user status srun-login.service --no-pager
journalctl --user -u srun-login.service -n 20 --no-pager
```

## 常见问题

### 运行后提示「已联网或未捕获到重定向查询串」，但实际没网

可能是网关没有把外网 HTTP 请求重定向到门户，或者当前设备处于「无感认证」窗口内。可先用浏览器访问一个 `http://`（注意不是 `https://`）的外网站点，确认是否真的被重定向到登录页。

### 登录接口返回「设备未注册」

说明当前设备的 MAC 还没有在该账号下认证过，需要在学校的自助服务系统里先添加/绑定设备，或手动登录一次让系统记住设备。

### 改了脚本不生效

定时器每 60 秒才运行一次，改动后可以手动触发：

```bash
systemctl --user start srun-login.service
```

## 免责声明

本项目仅用于学习与个人便利，请遵守所在学校/园区的网络使用规定。请在你自己有权使用的账号与设备上运行，不要用于绕过任何计费、身份或访问控制。

