const container = document.getElementById('danmaku-container');
const isSource = !!container;   // obs.html 管理页没有弹幕容器，避免重复连接/报错
let ws = null;
const MAX_ITEMS = 20; // 最多显示20条弹幕

// OBS 布局（各区块位置/大小，百分比）
const BLOCK_LABELS = { strength: '电流强度', price: '投喂价格表', danmaku: '弹幕列表' };
let obsLayout = null;
let obsDefaultLayout = null;

// URL 参数：?strength=0 关掉强度面板，?table=0 关掉价格表，?only=xxx 只渲染单个区块
const obsParams = new URLSearchParams(location.search);

// 单块模式：/obs/strength、/obs/price、/obs/danmaku 或 ?only=xxx
const ONLY_BLOCK = (function () {
    const injected = ((document.body && document.body.dataset && document.body.dataset.only) || '').toLowerCase();
    const fromQuery = (obsParams.get('only') || '').toLowerCase();
    const fromPath = ((location.pathname.match(/\/obs\/([a-z_]+)/i) || [])[1] || '').toLowerCase();
    const name = injected || fromQuery || fromPath;
    return ['strength', 'price', 'danmaku'].indexOf(name) >= 0 ? name : '';
})();
function obsFlag(name, def) {
    const v = obsParams.get(name);
    if (v === null || v === '') return def;
    return !['0', 'false', 'off', 'no'].includes(v.toLowerCase());
}

function connectWebSocket() {
    ws = new WebSocket(`ws://${location.host}/ws/obs`);
    
    ws.onopen = () => {
        console.log('WebSocket 已连接');
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'danmaku') {
            addDanmaku(msg.data);
        } else if (msg.type === 'gift') {
            addGift(msg.data);
        } else if (msg.type === 'sc') {
            addSuperChat(msg.data);
        } else if (msg.type === 'guard') {
            addGuard(msg.data);
        } else if (msg.type === 'strength') {
            updateStrength(msg.data);
        }
    };
    
    ws.onclose = () => {
        console.log('WebSocket 已断开，3秒后重连...');
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };
}

function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('zh-CN', { hour12: false });
}

function addDanmaku(data) {
    const item = document.createElement('div');
    item.className = 'danmaku-item';
    
    let badgeHtml = '';
    if (data.guard_level) {
        const guardNames = {1: '总督', 2: '提督', 3: '舰长'};
        badgeHtml = `<span class="danmaku-badge guard-${data.guard_level}">${guardNames[data.guard_level]}</span>`;
    }
    
    // 只在有头像URL时才显示头像
    const avatarHtml = data.face ? `<img src="${escapeHtml(data.face)}" class="danmaku-avatar" crossorigin="anonymous" referrerpolicy="no-referrer">` : '';
    
    item.innerHTML = `
        ${avatarHtml}
        <div class="danmaku-content">
            <div class="danmaku-user">
                <span class="danmaku-username">${escapeHtml(data.username)}</span>
                ${badgeHtml}
                <span class="danmaku-time">${getCurrentTime()}</span>
            </div>
            <div class="danmaku-message">${escapeHtml(data.message)}</div>
            ${data.dglab ? `
            <div class="dglab-info">
                <div class="dglab-strength">
                    <span class="dglab-strength-icon">⚡</span>
                    <span>+${data.dglab.strength}</span>
                </div>
                <div class="dglab-duration">
                    <span class="dglab-duration-icon">⏱️</span>
                    <span>${data.dglab.duration}</span>
                </div>
            </div>
            ` : ''}
        </div>
    `;
    
    container.appendChild(item);
    limitItems();
}

function addGift(data) {
    const item = document.createElement('div');
    item.className = 'danmaku-item gift';
    
    const avatarHtml = data.face ? `<img src="${escapeHtml(data.face)}" class="danmaku-avatar" crossorigin="anonymous" referrerpolicy="no-referrer">` : '';
    
    item.innerHTML = `
        ${avatarHtml}
        <div class="danmaku-content">
            <div class="danmaku-user">
                <span class="danmaku-username">${escapeHtml(data.username)}</span>
                <span class="danmaku-time">${getCurrentTime()}</span>
            </div>
            <div class="danmaku-message">
                赠送 <span class="gift-name">${escapeHtml(data.gift_name)}</span> 
                <span class="gift-count">x${data.count}</span>
                <span class="gift-price">¥${data.price}</span>
            </div>
            ${data.dglab ? `
            <div class="dglab-info">
                <div class="dglab-strength">
                    <span class="dglab-strength-icon">⚡</span>
                    <span>+${data.dglab.strength}</span>
                </div>
                <div class="dglab-duration">
                    <span class="dglab-duration-icon">⏱️</span>
                    <span>${data.dglab.duration}</span>
                </div>
            </div>
            ` : ''}
        </div>
    `;
    
    container.appendChild(item);
    limitItems();
}

function addSuperChat(data) {
    const item = document.createElement('div');
    item.className = 'danmaku-item sc';
    
    const avatarHtml = data.face ? `<img src="${escapeHtml(data.face)}" class="danmaku-avatar" crossorigin="anonymous" referrerpolicy="no-referrer">` : '';
    
    item.innerHTML = `
        ${avatarHtml}
        <div class="danmaku-content">
            <div class="danmaku-user">
                <span class="danmaku-username">${escapeHtml(data.username)}</span>
                <span class="danmaku-badge">SC ¥${data.price}</span>
                <span class="danmaku-time">${getCurrentTime()}</span>
            </div>
            <div class="danmaku-message">${escapeHtml(data.message)}</div>
            ${data.dglab ? `
            <div class="dglab-info">
                <div class="dglab-strength">
                    <span class="dglab-strength-icon">⚡</span>
                    <span>+${data.dglab.strength}</span>
                </div>
                <div class="dglab-duration">
                    <span class="dglab-duration-icon">⏱️</span>
                    <span>${data.dglab.duration}</span>
                </div>
            </div>
            ` : ''}
        </div>
    `;
    
    container.appendChild(item);
    limitItems();
}

function addGuard(data) {
    const item = document.createElement('div');
    item.className = 'danmaku-item guard';
    
    const guardNames = {1: '总督', 2: '提督', 3: '舰长'};
    
    item.innerHTML = `
        <div class="danmaku-user">
            <span class="danmaku-username">${escapeHtml(data.username)}</span>
            <span class="danmaku-badge guard-${data.guard_level}">开通${guardNames[data.guard_level]}</span>
            <span class="danmaku-time">${getCurrentTime()}</span>
        </div>
        ${data.dglab ? `
        <div class="dglab-info">
            <div class="dglab-strength">
                <span class="dglab-strength-icon">⚡</span>
                <span>+${data.dglab.strength}</span>
            </div>
            <div class="dglab-duration">
                <span class="dglab-duration-icon">⏱️</span>
                <span>${data.dglab.duration}</span>
            </div>
        </div>
        ` : ''}
    `;
    
    container.appendChild(item);
    limitItems();
}

function limitItems() {
    // 当超过最大数量时，移除最旧的（第一个）
    while (container.children.length > MAX_ITEMS) {
        container.removeChild(container.firstChild);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 初始化（仅 OBS 浏览器源页面）
if (isSource) {
    if (ONLY_BLOCK) {
        applySingleMode();
    } else {
        const editing = obsFlag('edit', false);
        initLayout(editing).then(() => {
            // 兼容旧参数：?strength=0 / ?table=0 / ?danmaku=0
            if (!obsFlag('strength', true)) obsLayout.strength.visible = false;
            if (!obsFlag('table', true)) obsLayout.price.visible = false;
            if (!obsFlag('danmaku', true)) obsLayout.danmaku.visible = false;
            applyLayout();
            if (editing) setupEditor();
        });
    }
    connectWebSocket();
    loadHistory();
    loadLive();
    loadPriceTable();
}

// ── OBS 地址（管理页用）─────────────────────────────────────────────
function buildObsUrl() {
    const url = new URL('/obs-source.html', location.origin);
    const strength = document.getElementById('opt-strength');
    const table = document.getElementById('opt-table');
    if (strength && !strength.checked) url.searchParams.set('strength', '0');
    if (table && !table.checked) url.searchParams.set('table', '0');
    return url.toString();
}

async function copyObsUrl() {
    const urlInput = document.getElementById('obs-url');
    if (!urlInput) return;
    const obsUrl = buildObsUrl();
    urlInput.value = obsUrl;
    if (navigator.clipboard) {
        try { await navigator.clipboard.writeText(obsUrl); } catch (e) { /* 忽略 */ }
    }
}

function refreshObsUrl() {
    const urlInput = document.getElementById('obs-url');
    if (!urlInput) return;
    const obsUrl = buildObsUrl();
    urlInput.value = obsUrl;
    // 预览用编辑模式（可拖动），但复制出去的地址不带 edit
    const frame = document.getElementById('obs-preview-frame');
    if (frame) {
        const edit = document.getElementById('opt-edit');
        const previewUrl = new URL(obsUrl);
        if (edit && edit.checked) previewUrl.searchParams.set('edit', '1');
        frame.src = previewUrl.toString();
    }
}

function copyUrl(id) {
    const el = document.getElementById(id);
    if (!el || !el.value) return;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(el.value).catch(() => {});
    } else {
        el.select();
        document.execCommand('copy');
    }
    el.style.borderColor = '#00d9ff';
    setTimeout(() => { el.style.borderColor = '#333'; }, 800);
}

window.addEventListener('DOMContentLoaded', () => {
    if (!isSource) {
        ['opt-strength', 'opt-table', 'opt-edit'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', refreshObsUrl);
        });
        // 三个独立源的固定链接
        ['strength', 'price', 'danmaku'].forEach(name => {
            const el = document.getElementById('url-' + name);
            if (el) el.value = location.origin + '/obs/' + name;
        });
        refreshObsUrl();
    }
});

async function loadHistory() {
    try {
        const resp = await fetch('/api/obs/history');
        const history = await resp.json();
        history.forEach(item => {
            if (item.type === 'danmaku') {
                addDanmaku(item.data);
            } else if (item.type === 'gift') {
                addGift(item.data);
            } else if (item.type === 'sc') {
                addSuperChat(item.data);
            } else if (item.type === 'guard') {
                addGuard(item.data);
            }
        });
    } catch (e) {
        console.error('加载历史记录失败:', e);
    }
}


// ── 实时电流强度 ──────────────────────────────────────────────────────
function setBar(fillId, numId, value, limit) {
    const fill = document.getElementById(fillId);
    const num = document.getElementById(numId);
    if (!fill || !num) return;
    const pct = limit > 0 ? Math.min(100, (value / limit) * 100) : 0;
    fill.style.width = pct.toFixed(1) + '%';
    num.textContent = limit > 0 ? (value + ' / ' + limit) : String(value);
}

function updateStrength(s) {
    if (!isSource || !s) return;
    setBar('fill-a', 'num-a', s.strength_a || 0, s.limit_a || 0);
    setBar('fill-b', 'num-b', s.strength_b || 0, s.limit_b || 0);

    const dot = document.getElementById('conn-dot');
    const text = document.getElementById('conn-text');
    if (dot && text) {
        dot.className = 'dot ' + (s.connected ? 'online' : 'offline');
        text.textContent = s.connected
            ? (s.enabled === false ? '已连接（控制器已禁用）' : '已连接')
            : '未连接';
    }
}

async function loadLive() {
    try {
        updateStrength(await (await fetch('/api/obs/live')).json());
    } catch (e) {
        console.error('加载实时强度失败:', e);
    }
}

// ── 投喂价格表 ────────────────────────────────────────────────────────
async function loadPriceTable() {
    const table = document.getElementById('price-table');
    if (!table) return;
    try {
        const t = await (await fetch('/api/obs/price-table')).json();
        const rows = [];
        if (t.danmaku && t.danmaku.enabled) {
            rows.push(['弹幕', '每条', '+' + t.danmaku.strength_add, t.danmaku.duration]);
        }
        (t.gift || []).forEach(x => rows.push(['礼物', '≥' + x.min_price + ' 元', '+' + x.strength_add, x.duration]));
        (t.super_chat || []).forEach(x => rows.push(['SC', '≥' + x.min_price + ' 元', '+' + x.strength_add, x.duration]));
        (t.guard || []).forEach(x => rows.push(['上舰', x.name, '+' + x.strength_add, x.duration]));
        (t.interact || []).forEach(x => rows.push(['互动', x.name, '+' + x.strength_add, x.duration]));

        if (!rows.length) {
            document.getElementById('price-panel').style.display = 'none';
            return;
        }
        table.innerHTML = '<tr><th>类型</th><th>条件</th><th>强度</th><th>持续</th></tr>' +
            rows.map(r =>
                '<tr><td class="pt-type">' + escapeHtml(r[0]) + '</td>' +
                '<td>' + escapeHtml(String(r[1])) + '</td>' +
                '<td class="pt-add">' + escapeHtml(String(r[2])) + '</td>' +
                '<td class="pt-dur">' + escapeHtml(String(r[3])) + '</td></tr>'
            ).join('');
    } catch (e) {
        console.error('加载价格表失败:', e);
    }
}


// ── OBS 布局（位置 / 大小，百分比）────────────────────────────────────
function stageEl() { return document.getElementById('obs-stage'); }
function blockEl(name) { return document.querySelector(`.obs-block[data-block="${name}"]`); }

async function initLayout(editing) {
    try {
        const data = await (await fetch('/api/obs/layout')).json();
        obsLayout = data.layout;
        obsDefaultLayout = data.default;
    } catch (e) {
        console.error('加载 OBS 布局失败，使用内置默认值', e);
        obsLayout = {
            strength: { x: 1, y: 1, w: 0, h: 0, visible: true },
            price: { x: 18, y: 1, w: 0, h: 0, visible: true },
            danmaku: { x: 1, y: 36, w: 30, h: 62, visible: true },
        };
        obsDefaultLayout = JSON.parse(JSON.stringify(obsLayout));
    }
}

function applyLayout() {
    if (!obsLayout) return;
    Object.keys(obsLayout).forEach(name => {
        const el = blockEl(name);
        if (!el) return;
        const cfg = obsLayout[name];
        el.style.left = cfg.x + '%';
        el.style.top = cfg.y + '%';
        el.style.width = cfg.w ? cfg.w + '%' : '';
        el.style.height = cfg.h ? cfg.h + '%' : '';
        el.classList.toggle('obs-hidden', cfg.visible === false);
        el.dataset.label = BLOCK_LABELS[name] || name;
    });
}

// ── 布局编辑器（?edit=1）──────────────────────────────────────────────
const EDIT_MARGIN = 0.3;   // 最小移动步长（%）

function blockRect(el) {
    const sr = stageEl().getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return {
        x: (r.left - sr.left) / sr.width * 100,
        y: (r.top - sr.top) / sr.height * 100,
        w: r.width / sr.width * 100,
        h: r.height / sr.height * 100,
    };
}

function setupEditor() {
    document.body.classList.add('obs-editing');

    document.querySelectorAll('.obs-block').forEach(el => {
        const grip = document.createElement('div');
        grip.className = 'obs-resize';
        el.appendChild(grip);

        el.addEventListener('dblclick', (e) => {
            e.preventDefault();
            const name = el.dataset.block;
            obsLayout[name].visible = obsLayout[name].visible === false;
            applyLayout();
            editMsg('已' + (obsLayout[name].visible ? '显示' : '隐藏') + '「' + (BLOCK_LABELS[name] || name) + '」，记得保存');
        });

        makeDraggable(el, 'move');
        makeDraggable(grip, 'resize', el);
    });

    document.querySelectorAll('#obs-edit-bar button').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.act === 'save') saveLayout();
            else if (btn.dataset.act === 'reset') resetLayout();
            else if (btn.dataset.act === 'exit') {
                const url = new URL(location.href);
                url.searchParams.delete('edit');
                location.href = url.toString();
            }
        });
    });

    editMsg('编辑模式：拖动左上角移动、右下角缩放、双击显示/隐藏');
}

function makeDraggable(handle, mode, block) {
    handle.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const el = block || handle.closest('.obs-block');
        const name = el.dataset.block;
        const sr = stageEl().getBoundingClientRect();
        const start = blockRect(el);
        const sx = e.clientX, sy = e.clientY;

        function onMove(ev) {
            const dx = (ev.clientX - sx) / sr.width * 100;
            const dy = (ev.clientY - sy) / sr.height * 100;
            if (mode === 'move') {
                obsLayout[name].x = Math.min(Math.max(0, round2(start.x + dx)), 100);
                obsLayout[name].y = Math.min(Math.max(0, round2(start.y + dy)), 100);
            } else {
                obsLayout[name].w = Math.min(Math.max(3, round2(start.w + dx)), 100);
                obsLayout[name].h = Math.min(Math.max(3, round2(start.h + dy)), 100);
            }
            applyLayout();
        }
        function onUp() {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            editMsg('位置已调整，点「保存布局」生效');
        }
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
    });
}

function round2(v) { return Math.round(v * 100) / 100; }

function editMsg(text, type) {
    const el = document.getElementById('obs-edit-msg');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'obs-edit-msg' + (type ? ' ' + type : '');
}

async function saveLayout() {
    try {
        const resp = await fetch('/api/obs/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ layout: obsLayout }),
        });
        const data = await resp.json();
        if (data.success) {
            obsLayout = data.layout;
            applyLayout();
            editMsg('✓ 布局已保存到 config.yaml', 'ok');
        } else {
            editMsg('保存失败：' + (data.error || '未知错误'), 'err');
        }
    } catch (e) {
        editMsg('保存失败：' + e.message, 'err');
    }
}

function resetLayout() {
    obsLayout = JSON.parse(JSON.stringify(obsDefaultLayout));
    applyLayout();
    editMsg('已恢复默认布局，点「保存布局」生效');
}


// ── 单块模式（独立浏览器源）──────────────────────────────────────────
function applySingleMode() {
    document.body.classList.add('obs-single');
    document.body.dataset.only = ONLY_BLOCK;   // 服务端已注入时是幂等的
    document.title = 'OBS 源 - ' + (BLOCK_LABELS[ONLY_BLOCK] || ONLY_BLOCK);

    ['strength', 'price', 'danmaku'].forEach(name => {
        const el = blockEl(name);
        if (!el) return;
        // 只显示目标区块；其余直接不渲染，避免空 div 影响源尺寸
        if (name === ONLY_BLOCK) {
            el.style.display = '';
            el.dataset.label = BLOCK_LABELS[name] || name;
        } else {
            el.style.display = 'none';
        }
    });

    const bar = document.getElementById('obs-edit-bar');
    if (bar) bar.style.display = 'none';
}
