#!/usr/bin/env node
/**
 * 深澜 srun「无线-v2」校园网自动登录脚本（浏览器自动化版）。
 *
 * 适用场景：学校使用深澜 srun 认证、登录页为 eportal 的「无线-v2」流程，
 * 且纯 HTTP 请求无法触发网关强制门户跳转（拿不到 wlanuserip/mac 参数）时。
 * 此时改用本机 Chrome 无头模式，让浏览器完整走完「跳转登录页 -> 填账号 -> 认证」。
 *
 * 依赖：puppeteer-core（npm install puppeteer-core），以及本机已安装 Chrome。
 */

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const os = require('os');
const path = require('path');
const https = require('https');

const CONFIG_PATH = path.join(os.homedir(), '.config', 'srun-login', 'config');
const CHROME_PATH = process.env.SRUN_CHROME || '/usr/bin/google-chrome';
const TRIGGER_URL = process.env.SRUN_TRIGGER_URL || 'http://www.baidu.com/';
const CHECK_URL = 'https://www.baidu.com/';


function loadCredential() {
  let user = process.env.SRUN_USER;
  let pass = process.env.SRUN_PASS;

  if ((!user || !pass) && fs.existsSync(CONFIG_PATH)) {
    for (const line of fs.readFileSync(CONFIG_PATH, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*(USERNAME|PASSWORD)\s*=\s*(.*?)\s*$/);
      if (m) {
        if (m[1] === 'USERNAME') user = m[2];
        else if (m[1] === 'PASSWORD') pass = m[2];
      }
    }
  }

  if (!user || !pass) {
    console.error('缺少账号信息：请在 ~/.config/srun-login/config 里配置 USERNAME/PASSWORD，或设置 SRUN_USER/SRUN_PASS 环境变量');
    process.exit(2);
  }
  return [user, pass];
}


function isOnline() {
  return new Promise((resolve) => {
    const req = https.get(CHECK_URL, { timeout: 4000 }, (res) => {
      res.resume();
      resolve(true);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}


async function main() {
  const [username, password] = loadCredential();

  if (await isOnline()) {
    console.log('已在线（已认证），无需登录');
    return;
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });

    // 访问普通 http 地址，触发网关强制门户跳转到登录页
    await page.goto(TRIGGER_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('#username', { timeout: 20000 });
    await page.waitForSelector('#pwd', { timeout: 20000 });

    // 直接给输入框赋值，并调用门户自己的 doauthen() 登录
    await page.evaluate((u, p) => {
      const userEl = document.getElementById('username');
      const pwdEl = document.getElementById('pwd');
      if (userEl) userEl.value = u;
      if (pwdEl) pwdEl.value = p;
      if (typeof doauthen === 'function') {
        doauthen();
      } else if (document.getElementById('loginLink')) {
        document.getElementById('loginLink').click();
      }
    }, username, password);

    // 等待认证生效，再探测外网连通性
    await new Promise((r) => setTimeout(r, 8000));
    await page.goto(CHECK_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    console.log('登录成功');
  } finally {
    await browser.close();
  }
}


main().catch((e) => {
  console.error('登录失败:', e.message);
  process.exit(1);
});
