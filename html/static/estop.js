/**
 * 紧急停堆悬浮按钮（桌宠式）
 *
 * 特点：
 *   - 固定悬浮在所有页面之上，可拖动，位置记在 localStorage
 *   - 一键：强度立即归零 + 关闭郊狼控制（并写回 config.yaml，重启后依然是关闭状态）
 *   - 再点一次可以恢复控制（带二次确认）
 *
 * 注意：obs-source.html（OBS 覆盖层）**不引入**本脚本，避免按钮出现在直播画面里。
 */
(function () {
    'use strict';
    if (window.__dglabEstopLoaded) return;
    window.__dglabEstopLoaded = true;

    const POS_KEY = 'dglab_estop_pos';
    const state = { enabled: true, online: true, busy: false, dragging: false, moved: false };
    let startX = 0, startY = 0, startLeft = 0, startTop = 0;

    // ── 样式（自注入，保证任何页面都能用）─────────────────────────────
    const style = document.createElement('style');
    style.textContent = `
    #estop-root {
        position: fixed; right: 24px; bottom: 24px; z-index: 2147483000;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif;
        user-select: none; -webkit-user-select: none; touch-action: none;
    }
    #estop-ball {
        position: relative; width: 76px; height: 76px; border-radius: 50%;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        cursor: grab; overflow: hidden;
        background: radial-gradient(circle at 32% 26%, #ff9aa9 0%, #e8436a 38%, #b3123c 72%, #7d0c2a 100%);
        box-shadow:
            0 1px 0 rgba(255,255,255,.35) inset,
            0 -8px 14px rgba(0,0,0,.28) inset,
            0 10px 26px rgba(179,18,60,.45),
            0 3px 8px rgba(0,0,0,.35);
        transition: transform .18s cubic-bezier(.2,.8,.3,1.2), box-shadow .25s ease, filter .2s ease;
        will-change: transform;
    }
    #estop-ball::before {
        content: ''; position: absolute; inset: 0; border-radius: 50%;
        box-shadow: 0 0 0 2px rgba(255,255,255,.28) inset; pointer-events: none;
    }
    #estop-ball .estop-shine {
        position: absolute; left: 14%; top: 8%; width: 58%; height: 38%;
        border-radius: 50%; pointer-events: none; filter: blur(1px);
        background: radial-gradient(ellipse at 50% 40%, rgba(255,255,255,.75), rgba(255,255,255,0) 70%);
    }
    #estop-ball:hover {
        transform: translateY(-2px) scale(1.05);
        box-shadow:
            0 1px 0 rgba(255,255,255,.4) inset,
            0 -8px 14px rgba(0,0,0,.28) inset,
            0 16px 34px rgba(179,18,60,.5),
            0 4px 10px rgba(0,0,0,.4);
    }
    #estop-ball:active { transform: scale(.97); cursor: grabbing; }
    #estop-ball .estop-emoji { font-size: 25px; line-height: 1; filter: drop-shadow(0 1px 1px rgba(0,0,0,.35)); }
    #estop-ball .estop-text {
        font-size: 10px; color: #fff; font-weight: 700; margin-top: 3px;
        letter-spacing: .6px; text-shadow: 0 1px 2px rgba(0,0,0,.4);
    }
    #estop-ball .estop-dot {
        position: absolute; right: 12px; top: 12px; width: 9px; height: 9px; border-radius: 50%;
        background: #22c55e; box-shadow: 0 0 0 2px rgba(255,255,255,.55), 0 0 8px rgba(34,197,94,.9);
        transition: background .2s ease, box-shadow .2s ease;
    }
    #estop-ball .estop-ring {
        position: absolute; inset: -8px; border-radius: 50%;
        border: 2px solid rgba(255,143,163,.75);
        animation: estop-pulse 2.4s cubic-bezier(.3,.7,.4,1) infinite;
        pointer-events: none;
    }
    #estop-ball .estop-ring.delay { animation-delay: 1.2s; }
    @keyframes estop-pulse {
        0%   { transform: scale(.92); opacity: .85; }
        75%  { transform: scale(1.28); opacity: 0; }
        100% { transform: scale(1.28); opacity: 0; }
    }
    #estop-root.disabled #estop-ball {
        background: radial-gradient(circle at 32% 26%, #e2e8f0 0%, #94a3b8 40%, #475569 75%, #334155 100%);
        box-shadow: 0 1px 0 rgba(255,255,255,.5) inset, 0 -8px 14px rgba(0,0,0,.25) inset, 0 8px 20px rgba(0,0,0,.35);
    }
    #estop-root.disabled #estop-ball .estop-ring { animation: none; opacity: 0; }
    #estop-root.offline #estop-ball {
        background: radial-gradient(circle at 32% 26%, #fde68a 0%, #f59e0b 40%, #b45309 75%, #78350f 100%);
        box-shadow: 0 1px 0 rgba(255,255,255,.45) inset, 0 -8px 14px rgba(0,0,0,.25) inset, 0 10px 26px rgba(180,83,9,.45);
    }
    #estop-root.offline #estop-ball .estop-ring { animation: none; opacity: 0; }
    #estop-root.busy #estop-ball { filter: grayscale(.35) brightness(.95); pointer-events: none; }
    #estop-panel {
        position: absolute; right: 0; bottom: 92px; width: 258px; display: none;
        background: linear-gradient(180deg, rgba(30,30,52,.99), rgba(20,20,36,.99));
        color: #e6e6ef; border: 1px solid rgba(255,77,109,.55); border-radius: 14px;
        padding: 15px; box-shadow: 0 18px 44px rgba(0,0,0,.7), 0 2px 6px rgba(0,0,0,.4);
        backdrop-filter: blur(12px); animation: estop-pop .16s ease-out;
    }
    @keyframes estop-pop { from { opacity: 0; transform: translateY(6px) scale(.98); } to { opacity: 1; transform: none; } }
    #estop-panel.show { display: block; }
    #estop-panel .estop-title {
        display: flex; align-items: center; gap: 7px;
        color: #ff8098; font-weight: 700; font-size: 13px; margin-bottom: 8px;
    }
    #estop-panel .estop-desc { font-size: 12px; line-height: 1.7; color: #aeb3c4; margin-bottom: 13px; }
    #estop-panel .estop-actions { display: flex; gap: 9px; }
    #estop-panel button {
        flex: 1; padding: 9px 0; border: none; border-radius: 8px;
        font-size: 13px; font-weight: 700; cursor: pointer;
        transition: transform .12s ease, opacity .15s ease, box-shadow .2s ease;
    }
    #estop-panel button:hover { opacity: .92; transform: translateY(-1px); }
    #estop-panel button:active { transform: translateY(0); }
    #estop-cancel { background: #33334d; color: #cfcfdd; }
    #estop-ok { background: linear-gradient(180deg, #e11d48, #a3123c); color: #fff; box-shadow: 0 4px 12px rgba(225,29,72,.4); }
    #estop-root.disabled #estop-ok { background: linear-gradient(180deg, #2563eb, #1d4ed8); box-shadow: 0 4px 12px rgba(37,99,235,.4); }
    #estop-toast {
        position: absolute; right: 0; bottom: 92px; width: 258px; display: none;
        background: linear-gradient(180deg, rgba(30,30,52,.99), rgba(20,20,36,.99));
        color: #e6e6ef; border-left: 4px solid #00d9ff; border-radius: 12px;
        padding: 12px 14px; font-size: 12px; line-height: 1.7;
        box-shadow: 0 16px 40px rgba(0,0,0,.65); animation: estop-pop .16s ease-out;
    }
    #estop-toast.show { display: block; }
    #estop-toast.error { border-left-color: #ff4d6d; }
`;
    document.head.appendChild(style);

    // ── DOM ───────────────────────────────────────────────────────────
    const root = document.createElement('div');
    root.id = 'estop-root';
    root.innerHTML = `
        <div id="estop-panel">
            <div class="estop-title"><span id="estop-panel-icon">🛑</span><span id="estop-panel-title">紧急停堆</span></div>
            <div class="estop-desc" id="estop-panel-desc"></div>
            <div class="estop-actions">
                <button id="estop-cancel">取消</button>
                <button id="estop-ok">立即停堆</button>
            </div>
        </div>
        <div id="estop-toast"></div>
        <div id="estop-ball" title="紧急停堆">
            <span class="estop-ring"></span>
            <span class="estop-ring delay"></span>
            <span class="estop-shine"></span>
            <span class="estop-emoji" id="estop-emoji">🛑</span>
            <span class="estop-text" id="estop-text">紧急停堆</span>
            <span class="estop-dot" id="estop-dot"></span>
        </div>
    `;

    const ball = root.querySelector('#estop-ball');
    const emoji = root.querySelector('#estop-emoji');
    const label = root.querySelector('#estop-text');
    const panel = root.querySelector('#estop-panel');
    const panelTitle = root.querySelector('#estop-panel-title');
    const panelDesc = root.querySelector('#estop-panel-desc');
    const okBtn = root.querySelector('#estop-ok');
    const cancelBtn = root.querySelector('#estop-cancel');
    const toastEl = root.querySelector('#estop-toast');

    // ── 位置：可拖动 + 记忆 ────────────────────────────────────────────
    function applyPos(left, top) {
        root.style.left = left + 'px';
        root.style.top = top + 'px';
        root.style.right = 'auto';
        root.style.bottom = 'auto';
    }

    function clampPos(left, top) {
        const w = root.offsetWidth || 90, h = root.offsetHeight || 90;
        return [
            Math.min(Math.max(4, left), Math.max(4, window.innerWidth - w - 4)),
            Math.min(Math.max(4, top), Math.max(4, window.innerHeight - h - 4)),
        ];
    }

    function savePos() {
        const r = root.getBoundingClientRect();
        try { localStorage.setItem(POS_KEY, JSON.stringify({ left: r.left, top: r.top })); } catch (e) { /* 忽略 */ }
    }

    function restorePos() {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(POS_KEY) || 'null'); } catch (e) { /* 忽略 */ }
        if (saved && typeof saved.left === 'number' && typeof saved.top === 'number') {
            const [left, top] = clampPos(saved.left, saved.top);
            applyPos(left, top);
        }
    }

    ball.addEventListener('pointerdown', (e) => {
        state.dragging = true;
        state.moved = false;
        startX = e.clientX; startY = e.clientY;
        const r = root.getBoundingClientRect();
        startLeft = r.left; startTop = r.top;
        try { ball.setPointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
    });

    ball.addEventListener('pointermove', (e) => {
        if (!state.dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (!state.moved && Math.abs(dx) < 5 && Math.abs(dy) < 5) return;  // 抖动阈值
        state.moved = true;
        const [left, top] = clampPos(startLeft + dx, startTop + dy);
        applyPos(left, top);
    });

    function endDrag(e) {
        if (!state.dragging) return;
        state.dragging = false;
        if (state.moved) savePos();
        try { ball.releasePointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
    }
    ball.addEventListener('pointerup', endDrag);
    ball.addEventListener('pointercancel', endDrag);

    // ── 提示条 ────────────────────────────────────────────────────────
    let toastTimer = null;
    function toast(text, isError) {
        panel.classList.remove('show');
        toastEl.textContent = text;
        toastEl.classList.toggle('error', !!isError);
        toastEl.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toastEl.classList.remove('show'), 5000);
    }

    // ── 状态刷新 ──────────────────────────────────────────────────────
    function render() {
        const disabled = state.enabled === false;
        const offline = state.online === false;
        root.classList.toggle('disabled', disabled);
        root.classList.toggle('busy', state.busy);
        root.classList.toggle('offline', offline && !disabled);

        const dot = root.querySelector('#estop-dot');
        if (dot) {
            if (offline && !disabled) {
                dot.style.background = '#f59e0b';
                dot.style.boxShadow = '0 0 0 2px rgba(255,255,255,.5), 0 0 8px rgba(245,158,11,.9)';
            } else if (disabled) {
                dot.style.background = '#94a3b8';
                dot.style.boxShadow = '0 0 0 2px rgba(255,255,255,.5)';
            } else {
                dot.style.background = '#22c55e';
                dot.style.boxShadow = '0 0 0 2px rgba(255,255,255,.55), 0 0 8px rgba(34,197,94,.9)';
            }
        }
        emoji.textContent = disabled ? '⏸️' : '🛑';
        label.textContent = disabled ? '已停堆' : '紧急停堆';
        ball.title = disabled
            ? '已紧急停堆（强度 0、控制已关闭），点击可恢复控制'
            : '紧急停堆：立即把 A/B 强度降到 0 并关闭控制';
    }

    async function refresh() {
        try {
            const resp = await fetch('/api/hub/status');
            const data = await resp.json();
            state.enabled = data.enabled !== false;
            state.online = true;
        } catch (e) {
            state.online = false;
        }
        render();
    }

    // ── 交互 ──────────────────────────────────────────────────────────
    function openPanel() {
        toastEl.classList.remove('show');
        const disabled = state.enabled === false;
        panelTitle.textContent = disabled ? '恢复郊狼控制' : '紧急停堆';
        const pIcon = root.querySelector('#estop-panel-icon');
        if (pIcon) pIcon.textContent = disabled ? '🔓' : '🛑';
        panelDesc.textContent = disabled
            ? '恢复后，弹幕 / 礼物 / SC / 上舰会重新控制郊狼设备。'
            : '立即把 A/B 强度降到 0 并关闭郊狼控制（写入配置，重启后仍是关闭状态）。';
        okBtn.textContent = disabled ? '恢复控制' : '立即停堆';
        panel.classList.add('show');
    }

    async function doAction() {
        panel.classList.remove('show');
        state.busy = true;
        render();
        const restoring = state.enabled === false;
        const url = restoring ? '/api/hub/resume' : '/api/hub/emergency-stop';
        try {
            const resp = await fetch(url, { method: 'POST' });
            const data = await resp.json();
            if (data.success) {
                state.enabled = data.enabled !== false;
                state.online = true;
                toast(data.message || (restoring ? '已恢复控制' : '已紧急停堆'), false);
            } else {
                toast('操作失败：' + (data.error || '未知错误'), true);
            }
        } catch (e) {
            state.online = false;
            toast('请求失败：' + e.message + '（主程序可能没在运行）', true);
        } finally {
            state.busy = false;
            render();
        }
    }

    ball.addEventListener('click', () => {
        if (state.moved) { state.moved = false; return; }   // 刚拖完，不算点击
        if (state.busy) return;
        openPanel();
    });
    okBtn.addEventListener('click', doAction);
    cancelBtn.addEventListener('click', () => panel.classList.remove('show'));

    document.addEventListener('click', (e) => {
        if (!root.contains(e.target)) panel.classList.remove('show');
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') panel.classList.remove('show');
    });
    window.addEventListener('resize', () => {
        const r = root.getBoundingClientRect();
        const [left, top] = clampPos(r.left, r.top);
        applyPos(left, top);
    });

    // ── 初始化 ────────────────────────────────────────────────────────
    function init() {
        document.body.appendChild(root);
        restorePos();
        render();
        refresh();
        setInterval(refresh, 4000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
