let currentConfig = null;

/** 读取等级配置，兼容 YAML 里的字符串键 '1'/'2'/'3' 与数字键 */
function levelConfig(mapping, level) {
    if (!mapping) return null;
    return mapping[level] ?? mapping[String(level)] ?? null;
}

let hubStatus = null;

async function loadConfig() {
    try {
        const [cfgResp, hubResp] = await Promise.all([
            fetch('/api/config/full'),
            fetch('/api/hub/status').catch(() => null)
        ]);
        currentConfig = await cfgResp.json();
        if (hubResp && hubResp.ok) {
            hubStatus = await hubResp.json();
        }
        populateForm(currentConfig);
        refreshLoginState();
    } catch (e) {
        showMessage('加载配置失败: ' + e.message, 'error');
    }
}

// ── 登录状态（扫一次就够了，这里显示当前是否还登录着）──
async function refreshLoginState() {
    const el = document.getElementById('login-state');
    if (!el) return;
    try {
        const d = await (await fetch('/api/bilibili/login')).json();
        if (d.is_login) {
            el.textContent = `✅ 已登录：${d.uname || ''}　（凭证已保存，重启自动恢复）`;
            el.style.color = '#00d9ff';
        } else if (d.has_saved_cookie) {
            el.textContent = '⚠️ 登录已失效，请重新扫码';
            el.style.color = '#ff6b6b';
        } else {
            el.textContent = '未登录（基础弹幕可用，扫码后数据更完整）';
            el.style.color = '#888';
        }
    } catch (e) {
        el.textContent = '无法获取登录状态';
        el.style.color = '#ff6b6b';
    }
}

function populateForm(config) {
    // Bilibili
    document.getElementById('room-id').value = config.bilibili.room_id || '';
    document.getElementById('sessdata').value = config.bilibili.sessdata || '';
    
    // Bilibili 登录模式
    const bili = config.bilibili || {};
    const modeEl = document.getElementById('bili-login-mode');
    if (modeEl) modeEl.value = bili.login_mode || 'always';

    // DG-Lab
    const dglab = config.dglab || {};
    document.getElementById('dglab-enabled').checked = dglab.enabled !== false;
    document.getElementById('dglab-mode').value = dglab.mode === 'remote' ? 'remote' : 'embedded';
    const channelSelect = document.getElementById('dglab-channel');
    if (channelSelect) {
        let channel = String(dglab.channel || '').toUpperCase();
        if (!channel) {
            channel = String(dglab.controller_id || '').toLowerCase().endsWith('.channelb') ? 'B' : 'A';
        }
        channelSelect.value = ['A', 'B', 'AB'].includes(channel) ? channel : 'A';
    }
    document.getElementById('dglab-client-id').value = dglab.client_id || 'blivedglab';
    document.getElementById('controller-url').value = dglab.controller_url || '';
    document.getElementById('controller-id').value = dglab.controller_id || '';
    renderPulseOptions(dglab.pulse_id);
    toggleDglabMode();
    
    // WebUI
    const webui = config.webui || {};
    document.getElementById('webui-host').value = webui.host || '0.0.0.0';
    document.getElementById('webui-port').value = webui.port || 17800;
    document.getElementById('exit-when-page-closed').checked = webui.exit_when_page_closed !== false;
    document.getElementById('count-obs-pages').checked = webui.count_obs_pages === true;
    
    // 弹幕
    document.getElementById('danmaku-enabled').checked = config.danmaku.enabled;
    document.getElementById('danmaku-strength').value = config.danmaku.strength_add;
    document.getElementById('danmaku-duration').value = config.danmaku.duration;
    
    // 限流
    const rateLimit = config.danmaku.rate_limit || {};
    document.getElementById('rate-limit-enabled').checked = rateLimit.enabled;
    document.getElementById('rate-limit-window').value = rateLimit.time_window || '1m';
    document.getElementById('rate-limit-count').value = rateLimit.max_count || 5;
    
    // 礼物
    document.getElementById('gift-enabled').checked = config.gift.enabled;
    renderTiers('gift', config.gift.tiers);
    
    // SC
    document.getElementById('sc-enabled').checked = config.super_chat.enabled;
    renderTiers('sc', config.super_chat.tiers);
    
    // 上舰
    document.getElementById('guard-enabled').checked = config.guard.enabled;
    // 注意：YAML 中的等级键是字符串 '1'/'2'/'3'，这里用 levelConfig 兼容 int/str 两种键
    const guardLevels = config.guard.levels || {};
    [3, 2, 1].forEach(lv => {
        const cfg = levelConfig(guardLevels, lv);
        if (!cfg) return;
        document.getElementById(`guard-${lv}-strength`).value = cfg.strength_add ?? '';
        document.getElementById(`guard-${lv}-duration`).value = cfg.duration ?? '';
    });
    
    // 互动
    const interact = config.interact || {};
    ['enter', 'follow', 'share', 'special_follow'].forEach(key => {
        const cfg = interact[key] || {};
        const enabled = document.getElementById(`interact-${key.replace('_', '-')}-enabled`);
        const strength = document.getElementById(`interact-${key.replace('_', '-')}-strength`);
        const duration = document.getElementById(`interact-${key.replace('_', '-')}-duration`);
        if (enabled) enabled.checked = cfg.enabled || false;
        if (strength) strength.value = cfg.strength_add || '';
        if (duration) duration.value = cfg.duration || '';
    });
}

function renderPulseOptions(selected) {
    const select = document.getElementById('dglab-pulse-id');
    if (!select) return;
    const pulses = (hubStatus && hubStatus.pulses) || [];
    select.innerHTML = '';
    pulses.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name ? `${p.name} (${p.id})` : p.id;
        select.appendChild(opt);
    });
    if (!pulses.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '（未能读取内置波形）';
        select.appendChild(opt);
    }
    if (selected && pulses.some(p => p.id === selected)) {
        select.value = selected;
    }
}

function toggleDglabMode() {
    const mode = document.getElementById('dglab-mode').value;
    document.querySelectorAll('.dglab-embedded-only').forEach(el => {
        el.style.display = mode === 'embedded' ? '' : 'none';
    });
    document.querySelectorAll('.dglab-remote-only').forEach(el => {
        el.style.display = mode === 'remote' ? '' : 'none';
    });
}

function renderTiers(type, tiers) {
    const container = document.getElementById(`${type}-tiers`);
    container.innerHTML = '';
    
    tiers.forEach((tier, index) => {
        const div = document.createElement('div');
        div.className = 'tier-item';
        div.innerHTML = `
            <input type="number" placeholder="最低价格" value="${tier.min_price}" data-field="min_price">
            <input type="number" placeholder="强度" value="${tier.strength_add}" data-field="strength_add">
            <input type="text" placeholder="持续时间" value="${tier.duration}" data-field="duration">
            <button class="btn-remove" onclick="removeTier('${type}', ${index})">删除</button>
        `;
        container.appendChild(div);
    });
}

function addGiftTier() {
    if (!currentConfig.gift.tiers) currentConfig.gift.tiers = [];
    currentConfig.gift.tiers.push({ min_price: 1, strength_add: 5, duration: '2m' });
    renderTiers('gift', currentConfig.gift.tiers);
}

function addSCTier() {
    if (!currentConfig.super_chat.tiers) currentConfig.super_chat.tiers = [];
    currentConfig.super_chat.tiers.push({ min_price: 30, strength_add: 15, duration: '10m' });
    renderTiers('sc', currentConfig.super_chat.tiers);
}

function removeTier(type, index) {
    const key = type === 'gift' ? 'gift' : 'super_chat';
    currentConfig[key].tiers.splice(index, 1);
    renderTiers(type, currentConfig[key].tiers);
}

function collectTiers(type) {
    const container = document.getElementById(`${type}-tiers`);
    const items = container.querySelectorAll('.tier-item');
    const tiers = [];
    
    items.forEach(item => {
        const inputs = item.querySelectorAll('input');
        const tier = {};
        inputs.forEach(input => {
            const field = input.dataset.field;
            let value = input.value;
            if (field === 'min_price' || field === 'strength_add') {
                value = parseFloat(value);
            }
            tier[field] = value;
        });
        tiers.push(tier);
    });
    
    return tiers;
}

async function saveConfig() {
    try {
        // 以当前配置为底稿，避免未在页面中展示的字段（如 guard_bonus）被丢弃
        const config = JSON.parse(JSON.stringify(currentConfig || {}));
        Object.assign(config, {
            // 用 Object.assign 合到原对象上，避免把扫码保存的 cookies 冲掉
            bilibili: Object.assign({}, currentConfig.bilibili, {
                // 允许填短号 / 直播间链接，后端会解析成真实房间号
                room_id: document.getElementById('room-id').value.trim(),
                sessdata: document.getElementById('sessdata').value,
                login_mode: document.getElementById('bili-login-mode').value
            }),
            dglab: Object.assign({}, currentConfig.dglab, {
                enabled: document.getElementById('dglab-enabled').checked,
                mode: document.getElementById('dglab-mode').value,
                channel: document.getElementById('dglab-channel').value,
                client_id: document.getElementById('dglab-client-id').value || 'blivedglab',
                pulse_id: document.getElementById('dglab-pulse-id').value,
                controller_url: document.getElementById('controller-url').value,
                controller_id: document.getElementById('controller-id').value
            }),
            // 同样用 Object.assign 合并：webui 下还有 exit_when_page_closed 等字段
            webui: Object.assign({}, currentConfig.webui, {
                host: document.getElementById('webui-host').value,
                port: parseInt(document.getElementById('webui-port').value),
                exit_when_page_closed: document.getElementById('exit-when-page-closed').checked,
                count_obs_pages: document.getElementById('count-obs-pages').checked
            }),
            danmaku: {
                enabled: document.getElementById('danmaku-enabled').checked,
                strength_add: parseInt(document.getElementById('danmaku-strength').value),
                duration: document.getElementById('danmaku-duration').value,
                rate_limit: {
                    enabled: document.getElementById('rate-limit-enabled').checked,
                    time_window: document.getElementById('rate-limit-window').value,
                    max_count: parseInt(document.getElementById('rate-limit-count').value)
                },
                guard_bonus: currentConfig.danmaku.guard_bonus || {}
            },
            interact: {
                enter: {
                    enabled: document.getElementById('interact-enter-enabled').checked,
                    strength_add: parseInt(document.getElementById('interact-enter-strength').value) || 1,
                    duration: document.getElementById('interact-enter-duration').value || '30s'
                },
                follow: {
                    enabled: document.getElementById('interact-follow-enabled').checked,
                    strength_add: parseInt(document.getElementById('interact-follow-strength').value) || 3,
                    duration: document.getElementById('interact-follow-duration').value || '30s'
                },
                share: {
                    enabled: document.getElementById('interact-share-enabled').checked,
                    strength_add: parseInt(document.getElementById('interact-share-strength').value) || 2,
                    duration: document.getElementById('interact-share-duration').value || '1m'
                },
                special_follow: {
                    enabled: document.getElementById('interact-special-follow-enabled').checked,
                    strength_add: parseInt(document.getElementById('interact-special-follow-strength').value) || 2,
                    duration: document.getElementById('interact-special-follow-duration').value || '30s'
                }
            },
            gift: {
                enabled: document.getElementById('gift-enabled').checked,
                tiers: collectTiers('gift')
            },
            super_chat: {
                enabled: document.getElementById('sc-enabled').checked,
                tiers: collectTiers('sc')
            },
            guard: {
                enabled: document.getElementById('guard-enabled').checked,
                levels: (() => {
                    const levels = {};
                    [1, 2, 3].forEach(lv => {
                        const old = levelConfig(currentConfig.guard && currentConfig.guard.levels, lv) || {};
                        const strength = document.getElementById(`guard-${lv}-strength`).value;
                        const duration = document.getElementById(`guard-${lv}-duration`).value;
                        levels[String(lv)] = {
                            strength_add: strength === '' ? (old.strength_add ?? 0) : parseInt(strength),
                            duration: duration || old.duration || '30s'
                        };
                    });
                    return levels;
                })()
            },
            log: currentConfig.log || { level: 'INFO' }
        });
        
        const resp = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await resp.json();
        if (result.success) {
            showMessage(result.message || '配置已保存并生效！', 'success');
            // 重新加载配置以显示最新值
            setTimeout(() => loadConfig(), 500);
        } else {
            showMessage('保存失败: ' + result.error, 'error');
        }
    } catch (e) {
        showMessage('保存失败: ' + e.message, 'error');
    }
}

function showMessage(text, type) {
    const msg = document.getElementById('save-message');
    msg.textContent = text;
    msg.className = type;
    setTimeout(() => {
        msg.style.display = 'none';
    }, 5000);
}

// 环境自检：缺 ruamel.yaml 会丢注释，必须让用户看见
async function checkHealth() {
    try {
        const h = await (await fetch('/api/health')).json();
        const box = document.getElementById('dep-warning');
        if (box && h.ruamel === false) box.style.display = '';
    } catch (e) { /* 忽略 */ }
}

// 初始化
document.getElementById('dglab-mode').addEventListener('change', toggleDglabMode);
checkHealth();
loadConfig();

// 平滑滚动到锚点
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href').substring(1);
        const target = document.getElementById(targetId);
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // 高亮效果
            target.style.transition = 'box-shadow 0.3s';
            target.style.boxShadow = '0 0 20px rgba(0, 217, 255, 0.5)';
            setTimeout(() => {
                target.style.boxShadow = '';
            }, 1000);
        }
    });
});


// ── Bilibili 扫码登录 ────────────────────────────────────────────────
let qrKey = null;
let qrTimer = null;

function stopQrLogin() {
    if (qrTimer) { clearInterval(qrTimer); qrTimer = null; }
    qrKey = null;
    const box = document.getElementById('qr-box');
    if (box) box.style.display = 'none';
    const btn = document.getElementById('qr-start');
    if (btn) { btn.disabled = false; btn.textContent = '显示二维码'; }
}

async function startQrLogin() {
    const btn = document.getElementById('qr-start');
    const hint = document.getElementById('qr-hint');
    btn.disabled = true;
    btn.textContent = '生成中…';
    const hintEl = document.getElementById('qr-hint');
    if (hintEl) { hintEl.style.color = '#888'; }
    try {
        const data = await (await fetch('/api/bilibili/qrcode', { method: 'POST' })).json();
        if (!data.success) {
            hint.textContent = '生成二维码失败：' + (data.error || '未知错误');
            hint.style.color = '#ff6b6b';
            btn.disabled = false;
            btn.textContent = '重试';
            return;
        }
        qrKey = data.key;
        document.getElementById('qr-img').innerHTML = data.qr_svg;
        document.getElementById('qr-box').style.display = '';
        document.getElementById('qr-state').textContent = '等待扫码…（二维码 3 分钟内有效）';
        btn.textContent = '刷新二维码';
        btn.disabled = false;
        clearInterval(qrTimer);
        qrTimer = setInterval(pollQrLogin, 2000);
    } catch (e) {
        hint.textContent = '生成二维码失败：' + e.message;
        hint.style.color = '#ff6b6b';
        btn.disabled = false;
        btn.textContent = '重试';
    }
}

async function pollQrLogin() {
    if (!qrKey) return;
    const state = document.getElementById('qr-state');
    try {
        const data = await (await fetch('/api/bilibili/qrcode/status?key=' + encodeURIComponent(qrKey))).json();
        if (!data.success) {
            state.textContent = '查询失败：' + (data.error || '未知错误');
            state.style.color = '#ff6b6b';
            return;
        }
        if (!data.login) {
            state.textContent = data.message || '等待扫码…';
            state.style.color = data.expired ? '#ff6b6b' : '#e0e0e0';
            if (data.expired) { clearInterval(qrTimer); qrTimer = null; }
            return;
        }
        // 登录成功
        clearInterval(qrTimer);
        qrTimer = null;
        const room = data.room || {};
        state.textContent = `✅ 登录成功！直播间：${room.uname || ''} ${room.room_id || ''}`;
        state.style.color = '#00d9ff';
        const hint = document.getElementById('qr-hint');
        hint.textContent = '已自动填入 SESSDATA 和直播间号，登录凭证已保存，下次启动不用再扫';
        hint.style.color = '#00d9ff';
        setTimeout(() => { loadConfig(); stopQrLogin(); }, 600);
    } catch (e) {
        state.textContent = '查询失败：' + e.message;
        state.style.color = '#ff6b6b';
    }
}

async function resolveRoom() {
    const input = document.getElementById('room-id');
    const hint = document.getElementById('room-hint');
    const value = input.value.trim();
    if (!value) { hint.textContent = '请先填房间号或粘贴直播间链接'; hint.style.color = '#ff6b6b'; return; }
    hint.textContent = '解析中…';
    hint.style.color = '#888';
    try {
        const data = await (await fetch('/api/bilibili/room/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room: value })
        })).json();
        if (!data.success) {
            hint.textContent = '解析失败：' + (data.error || '未知错误');
            hint.style.color = '#ff6b6b';
            return;
        }
        const room = data.room || {};
        input.value = room.room_id || value;
        hint.textContent = `✅ 已解析并切换：${room.uname || ''} ${room.title ? '· ' + room.title : ''}（房间号 ${room.room_id}）`;
        hint.style.color = '#00d9ff';
    } catch (e) {
        hint.textContent = '解析失败：' + e.message;
        hint.style.color = '#ff6b6b';
    }
}
