/* 「页面存在」心跳 —— 由服务端自动注入到每个页面
 * 作用：主程序据此判断还有没有网页开着，全部关掉后自动退出。
 * 说明：不需要时可在 config.yaml 里把 webui.exit_when_page_closed 设为 false。
 */
(function () {
    'use strict';
    if (window.__blivePresence) { return; }
    window.__blivePresence = true;

    // /obs/... 是给 OBS 用的覆盖层页面
    var isObsPage = location.pathname.indexOf('/obs') === 0;
    // 但「OBS 里的浏览器源」和「浏览器里打开的 obs 页面」要区分开：
    // OBS 的浏览器源会注入 window.obsstudio，UA 里也带着 obs-browser。
    // 前者不能算「有人在看网页」，后者（自己用浏览器打开预览）必须算，
    // 否则在 OBS 页面上停留会被误判成「网页都关了」。
    var inObsStudio = !!window.obsstudio ||
        /obs-browser|OBS-Studio|obs-studio/i.test(navigator.userAgent || '');

    var id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    var params = '?id=' + encodeURIComponent(id) + (isObsPage ? '&obs=1' : '');
    if (inObsStudio) { params += '&embed=1'; }
    var base = '/api/page/heartbeat' + params;
    var leaveUrl = '/api/page/leave?id=' + encodeURIComponent(id);
    var INTERVAL = 2500;

    function beat() {
        try {
            fetch(base, { method: 'POST', cache: 'no-store', keepalive: true })['catch'](function () {});
        } catch (e) { /* 忽略 */ }
    }

    function leave() {
        try {
            if (navigator.sendBeacon) {
                navigator.sendBeacon(leaveUrl);
            } else {
                fetch(leaveUrl, { method: 'POST', cache: 'no-store', keepalive: true })['catch'](function () {});
            }
        } catch (e) { /* 忽略 */ }
    }

    beat();
    setInterval(beat, INTERVAL);
    // 后台标签页会被浏览器降频，切回前台时立刻补一次心跳
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) { beat(); }
    });
    // 关标签页 / 刷新 / 跳转：用 sendBeacon 保证请求发得出去
    window.addEventListener('pagehide', leave);
    window.addEventListener('unload', leave);
})();
