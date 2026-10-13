// 郊狼控制页面脚本
let lastMode = null;
let currentStatus = null;
let qrFormat = 'link';

function $(id) { return document.getElementById(id); }

async function refreshStatus() {
    try {
        const resp = await fetch('/api/hub/status');
        const data = await resp.json();
        currentStatus = data;
        render(data);
    } catch (e) {
        // 忽略轮询错误
    }
}

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
}

function setValue(id, value) {
    const el = $(id);
    if (el) el.value = value == null ? '' : value;
}

function render(s) {
    const embedded = s.mode !== 'remote';

    const modeText = embedded ? '内置郊狼服务' : '外部 Game Hub';
    setText('mode-label', s.enabled ? modeText : (modeText + '（已禁用）'));
    setText('client-id', s.client_id || '-');
    setText('target-id', s.target_id || '-');
    setText('strength-a', s.connected ? (s.strength_a + ' / ' + s.limit_a + '（目标 ' + s.target_a + '）') : '-');
    setText('strength-b', s.connected ? (s.strength_b + ' / ' + s.limit_b + '（目标 ' + s.target_b + '）') : '-');
    setText('limit-info', 'A: ' + (s.limit_a || 0) + ' / B: ' + (s.limit_b || 0));

    const statusEl = $('conn-status');
    statusEl.textContent = s.connected ? '已连接' : '未连接';
    statusEl.className = 'status ' + (s.connected ? 'online' : 'offline');

    $('embedded-panel').style.display = embedded ? '' : 'none';
    $('manual-panel').style.display = (embedded && s.enabled) ? '' : 'none';
    $('remote-panel').style.display = embedded ? 'none' : '';

    if (!embedded) {
        const url = s.controller_url || 'http://127.0.0.1:8920';
        setValue('remote-url', url);
        if (lastMode !== 'remote') {
            $('remote-frame').src = url;
        }
    } else {
        setValue('ws-url', s.ws_url);
        setValue('client-id-field', s.client_id);
        setText('addr-host', s.connect_host || '-');
        setText('addr-port', s.connect_port || '-');
        setText('addr-path', '/dglab_ws/' + (s.client_id || ''));

        // 诊断信息 + 局域网未开启告警
        setText('diag-bind', (s.bound_addresses || []).join(', ') || s.bind_host || '-');
        setText('diag-advertise', (s.connect_host || '-') + ':' + (s.connect_port || '-'));
        const diagLan = $('diag-lan');
        diagLan.textContent = s.lan_ready ? '局域网可达 ✓' : '仅本机可达 ✗';
        diagLan.style.color = s.lan_ready ? '#00d9ff' : '#ff6b6b';

        const warn = $('lan-warning');
        if (warn) {
            warn.style.display = s.lan_ready ? 'none' : '';
            setText('lan-bind', (s.bound_addresses || []).join(', ') || s.bind_host || '-');
        }
        setValue('pulse-name', s.pulse ? (s.pulse + ' (' + s.pulse_id + ')') : '-');

        const qr = $('qr-img');
        if (qr && qr.dataset.boundUrl !== s.ws_url) {
            qr.dataset.boundUrl = s.ws_url;
            reloadQr();
        }
    }
    lastMode = s.mode;
}

async function allowLan() {
    const msg = $('lan-message');
    msg.textContent = '正在切换...';
    msg.style.color = '#888';
    try {
        const resp = await fetch('/api/hub/allow-lan', { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            msg.textContent = data.message || '已开启';
            msg.style.color = '#00d9ff';
            await refreshStatus();
        } else {
            msg.textContent = data.error || '切换失败';
            msg.style.color = '#ff6b6b';
        }
    } catch (e) {
        msg.textContent = '请求失败：' + e.message;
        msg.style.color = '#ff6b6b';
    }
}

function reloadQr() {
    const qr = $('qr-img');
    if (!qr) return;
    qr.src = '/api/hub/qrcode?format=' + qrFormat + '&t=' + Date.now();
}

function setQrFormat(fmt) {
    qrFormat = fmt;
    reloadQr();
}

function copyField(id) {
    const el = $(id);
    if (!el || !el.value) return;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(el.value);
    } else {
        el.select();
        document.execCommand('copy');
    }
    showManualMessage('已复制：' + el.value, 'online');
}

async function manual(action, channel, value) {
    const body = { channel: channel };
    if (action === 'add') body.add = 1;
    else if (action === 'sub') body.sub = 1;
    else body.set = value || 0;

    try {
        const resp = await fetch('/api/hub/strength', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await resp.json();
        if (data.success) {
            const base = 'A:' + data.status.strength_a + '  B:' + data.status.strength_b;
            if (data.clamped && data.message) {
                showManualMessage(base + '  ⚠️ ' + data.message, 'warn');
            } else {
                showManualMessage(base, 'online');
            }
        } else {
            showManualMessage(data.error || '操作失败', 'offline');
        }
    } catch (e) {
        showManualMessage('请求失败: ' + e.message, 'offline');
    }
    refreshStatus();
}

function showManualMessage(text, type) {
    const el = $('manual-message');
    if (!el) return;
    el.textContent = text;
    el.style.color = type === 'online' ? '#00d9ff' : (type === 'warn' ? '#ffb454' : '#ff6b6b');
    clearTimeout(showManualMessage._timer);
    showManualMessage._timer = setTimeout(() => { el.textContent = ''; }, 5000);
}

function openRemote() {
    const url = $('remote-url').value;
    if (url) window.open(url, '_blank');
}

// 二维码生成失败（缺少 qrcode 依赖）时的降级提示
$('qr-img').addEventListener('error', () => {
    const wsUrl = $('ws-url') ? $('ws-url').value : '';
    const box = $('qr-img').parentElement;
    box.innerHTML = '<div style="color:#000; font-size:12px; padding:8px; word-break:break-all;">'
        + '无法生成二维码（缺少 qrcode 依赖，请执行 pip install -r requirements.txt）<br><br>'
        + '可直接在 App 里手动填写地址：<br><b>' + wsUrl + '</b></div>';
});

refreshStatus();
setInterval(refreshStatus, 2000);
