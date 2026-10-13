// 扫码登录页：进来自动出二维码，扫完自动跳转
let qrKey = null;
let timer = null;
let done = false;

function $(id) { return document.getElementById(id); }

function setState(title, desc, maskText) {
    $('state-title').textContent = title;
    if (desc !== undefined) $('state-desc').textContent = desc;
    const mask = $('qr-mask');
    if (maskText === null) {
        mask.style.display = 'none';
    } else {
        mask.style.display = '';
        mask.textContent = maskText;
    }
}

async function refreshNowState() {
    try {
        const d = await (await fetch('/api/bilibili/login')).json();
        const el = $('now-state');
        if (d.is_login) {
            el.className = 'badge ok';
            el.textContent = '已登录 ' + (d.uname || '');
        } else if (d.has_saved_cookie) {
            el.className = 'badge warn';
            el.textContent = '凭证已失效，请重新扫码';
        } else {
            el.className = 'badge dim';
            el.textContent = '未登录';
        }
    } catch (e) {
        $('now-state').className = 'badge warn';
        $('now-state').textContent = '无法获取状态';
    }
}

async function startLogin() {
    if (done) return;
    clearInterval(timer);
    setState('正在生成二维码…', '请稍候', '生成中…');
    try {
        const data = await (await fetch('/api/bilibili/qrcode', { method: 'POST' })).json();
        if (!data.success) {
            setState('生成二维码失败', data.error || '未知错误', '生成失败，点「刷新二维码」重试');
            return;
        }
        qrKey = data.key;
        $('qr-wrap').innerHTML = data.qr_svg;
        setState('等待扫码', '用手机哔哩哔哩 App 扫一扫，二维码 3 分钟内有效', null);
        timer = setInterval(poll, 2000);
    } catch (e) {
        setState('生成二维码失败', e.message, '点「刷新二维码」重试');
    }
}

async function poll() {
    if (!qrKey || done) return;
    try {
        const data = await (await fetch('/api/bilibili/qrcode/status?key=' + encodeURIComponent(qrKey))).json();
        if (!data.success) return;
        if (!data.login) {
            if (data.expired) {
                clearInterval(timer);
                setState('二维码已过期', '请点「刷新二维码」重新获取', '已过期，点下方按钮刷新');
            } else if (data.message && data.message.indexOf('已扫') >= 0) {
                setState('已扫码', '请在手机上点击「确认登录」', null);
            }
            return;
        }
        // 登录成功
        done = true;
        clearInterval(timer);
        const room = data.room || {};
        setState('✅ 登录成功', `直播间：${room.uname || ''} ${room.room_id || ''}`, null);
        $('tip').textContent = '登录凭证已刷新并保存，1.5 秒后进入控制台…';
        $('tip').style.color = '#00d9ff';
        setTimeout(() => { location.href = '/config.html'; }, 1500);
    } catch (e) {
        // 网络抖动，下一轮继续
    }
}

refreshNowState();
startLogin();
