const danmakuLogsDiv = document.getElementById('danmaku-logs');
const dglabLogsDiv = document.getElementById('dglab-logs');
let ws = null;

function connectWebSocket() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    
    ws.onopen = () => {
        console.log('WebSocket 已连接');
        document.getElementById('status').textContent = '运行中';
        document.getElementById('status').className = 'status online';
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'log') {
            const logType = msg.log_type || 'all';
            if (logType === 'danmaku') {
                addLog(danmakuLogsDiv, msg.data);
            } else if (logType === 'dglab') {
                addLog(dglabLogsDiv, msg.data);
            } else {
                // 其他日志不显示在首页
            }
        }
    };
    
    ws.onclose = () => {
        console.log('WebSocket 已断开，3秒后重连...');
        document.getElementById('status').textContent = '断开连接';
        document.getElementById('status').className = 'status offline';
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };
}

function addLog(container, log) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="log-time">[${log.time}]</span> <span class="log-${log.level}">[${log.level}]</span> <span class="log-message">${escapeHtml(log.message)}</span>`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
    
    // 限制日志条数
    while (container.children.length > 100) {
        container.removeChild(container.firstChild);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const config = await resp.json();
        document.getElementById('room-id').textContent = config.bilibili.room_id;
        document.getElementById('controller-id').textContent = config.dglab.controller_id;
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}

async function loadLogs() {
    try {
        // 加载弹幕日志
        const danmakuResp = await fetch('/api/logs?type=danmaku');
        const danmakuLogs = await danmakuResp.json();
        danmakuLogs.forEach(log => addLog(danmakuLogsDiv, log));
        
        // 加载郊狼日志
        const dglabResp = await fetch('/api/logs?type=dglab');
        const dglabLogs = await dglabResp.json();
        dglabLogs.forEach(log => addLog(dglabLogsDiv, log));
    } catch (e) {
        console.error('加载日志失败:', e);
    }
}

// 直播间监听状态（真实连接情况，出问题能一眼看到）
async function updateBiliStatus() {
    const el = document.getElementById('bili-status');
    const errBox = document.getElementById('bili-error');
    if (!el) return;
    try {
        const data = await (await fetch('/api/status')).json();
        const b = data.bilibili || {};
        const roomEl = document.getElementById('room-id');
        if (roomEl && b.room_id) roomEl.textContent = b.room_id;

        if (b.connected) {
            el.textContent = `监听中（已收 ${b.message_count || 0} 条）`;
            el.className = 'status online';
            if (errBox) errBox.style.display = 'none';
        } else {
            el.textContent = b.last_error ? '监听异常' : '连接中…';
            el.className = 'status offline';
            if (errBox) {
                if (b.last_error) {
                    errBox.style.display = '';
                    errBox.textContent = `直播间监听错误：${b.last_error}`
                        + (b.retry_count ? `（已尝试重连 ${b.retry_count} 次）` : '');
                } else {
                    errBox.style.display = 'none';
                }
            }
        }
    } catch (e) {
        el.textContent = '无法获取状态';
        el.className = 'status offline';
    }
}

// 初始化
loadConfig();
loadLogs();
connectWebSocket();
updateBiliStatus();
setInterval(updateBiliStatus, 3000);

// OBS 弹窗功能
function showObsModal() {
    const modal = document.getElementById('obs-modal');
    const urlInput = document.getElementById('obs-url');
    const obsUrl = `${window.location.protocol}//${window.location.host}/obs.html`;
    urlInput.value = obsUrl;
    modal.style.display = 'block';
}

function closeObsModal() {
    const modal = document.getElementById('obs-modal');
    modal.style.display = 'none';
}

async function copyObsUrl() {
    const urlInput = document.getElementById('obs-url');
    await navigator.clipboard.writeText(urlInput.value);
}

// 点击弹窗外部关闭
window.onclick = function(event) {
    const modal = document.getElementById('obs-modal');
    if (event.target === modal) {
        closeObsModal();
    }
}
