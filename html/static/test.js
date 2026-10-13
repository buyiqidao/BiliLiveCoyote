// 本地模拟直播间测试页
const INTERACT_BY_LEVEL = {1: 'enter', 2: 'follow', 3: 'share', 4: 'special_follow'};

function $(id) { return document.getElementById(id); }

function showMessage(text, ok) {
    const el = $('send-message');
    el.textContent = text;
    el.style.color = ok ? '#00d9ff' : '#ff6b6b';
    clearTimeout(showMessage._timer);
    showMessage._timer = setTimeout(() => { el.textContent = ''; }, 4000);
}

async function loadStatus() {
    let data;
    try {
        data = await (await fetch('/api/test/status')).json();
    } catch (e) {
        data = { enabled: false };
    }
    if (!data.enabled) {
        $('not-enabled').style.display = '';
        $('test-body').style.display = 'none';
        return false;
    }
    $('not-enabled').style.display = 'none';
    $('test-body').style.display = '';
    renderStatus(data);
    return true;
}

function renderStatus(s) {
    const stats = s.stats || {};
    const total = s.total || 0;
    const names = {
        'DANMU_MSG': '弹幕', 'SEND_GIFT': '礼物', 'SUPER_CHAT_MESSAGE': '醒目留言',
        'USER_TOAST_MSG_V2': '上舰', 'INTERACT_WORD_V2': '互动'
    };
    const items = [['合计', total]].concat(
        Object.keys(stats).sort().map(k => [names[k] || k, stats[k]])
    );
    $('stats').innerHTML = items.map(([k, v]) =>
        `<div class="config-item"><div class="config-label">${k}</div>` +
        `<div class="config-value">${v}</div></div>`).join('');

    const recent = s.recent || [];
    $('recent').innerHTML = recent.length
        ? recent.map(r => `<div class="log-entry"><span class="log-time">[${r.time}]</span> ` +
                          `<span style="color:#00d9ff;">[${names[r.cmd] || r.cmd}]</span> ` +
                          `<span class="log-message">${escapeHtml(r.summary)}</span></div>`).join('')
        : '<div style="color:#666; font-size:13px;">还没有发送过事件</div>';

    $('auto-state').textContent = s.auto
        ? `运行中（间隔 ${s.auto_interval}s）` : '已停止';
    $('auto-btn').textContent = s.auto ? '⏸️ 停止' : '▶️ 开始';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function collectPayload() {
    const type = $('evt-type').value;
    const username = $('evt-username').value.trim();
    const message = $('evt-message').value.trim();
    const count = parseInt($('evt-count').value) || 1;
    const interval = parseFloat($('evt-interval').value) || 0;
    const price = $('evt-price').value === '' ? null : parseFloat($('evt-price').value);
    const level = parseInt($('evt-level').value);

    const payload = { type, username, count, interval };
    if (type === 'danmaku') {
        payload.message = message;
        payload.guard_level = [1, 2, 3].includes(level) ? level : 0;
    } else if (type === 'gift') {
        payload.gift_name = message;
        payload.price = price;
    } else if (type === 'super_chat') {
        payload.message = message;
        payload.price = price;
    } else if (type === 'guard') {
        payload.level = [1, 2, 3].includes(level) ? level : 3;
    } else if (type === 'interact') {
        payload.action = INTERACT_BY_LEVEL[level] || 'enter';
    }
    return payload;
}

async function post(url, body) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    return await resp.json();
}

async function sendEvent() {
    try {
        const data = await post('/api/test/event', collectPayload());
        if (data.success) {
            const sent = data.sent || 1;
            showMessage(`已发送 ${sent} 条`, true);
            if (data.status) renderStatus(data.status);
        } else {
            showMessage(data.error || '发送失败', false);
        }
    } catch (e) {
        showMessage('请求失败: ' + e.message, false);
    }
}

async function quick(type, extra) {
    const payload = Object.assign({ type, count: 1, interval: 0 }, extra || {});
    try {
        const data = await post('/api/test/event', payload);
        if (data.success) {
            showMessage('已发送：' + (data.result ? data.result.summary : type), true);
            if (data.status) renderStatus(data.status);
        } else {
            showMessage(data.error || '发送失败', false);
        }
    } catch (e) {
        showMessage('请求失败: ' + e.message, false);
    }
}

async function burst(kind, count) {
    try {
        const data = await post('/api/test/event', { type: kind, count, interval: 0.05 });
        showMessage(data.success ? `已连发 ${data.sent} 条` : (data.error || '发送失败'), data.success);
        if (data.status) renderStatus(data.status);
    } catch (e) {
        showMessage('请求失败: ' + e.message, false);
    }
}

async function toggleAuto() {
    const running = $('auto-btn').textContent.indexOf('停止') >= 0;
    try {
        const data = await post('/api/test/auto', {
            enabled: !running,
            interval: parseFloat($('auto-interval').value) || 1
        });
        if (data.status) renderStatus(data.status);
    } catch (e) {
        showMessage('请求失败: ' + e.message, false);
    }
}

// 类型切换时给输入框更贴切的提示
$('evt-type').addEventListener('change', () => {
    const type = $('evt-type').value;
    const placeholder = {
        danmaku: '弹幕内容（留空随机）',
        gift: '礼物名（留空随机）',
        super_chat: 'SC 内容',
        guard: '（上舰不需要内容）',
        interact: '（互动不需要内容）',
        random: '（随机事件不需要内容）'
    };
    $('evt-message').placeholder = placeholder[type] || '';
});

loadStatus();
setInterval(loadStatus, 2000);
