(function () {
    'use strict';
    var endpoint = '/plugins/automation_rules/notifications_json';
    var storagePrefix = 'ospy-automation-notification-';
    var pending = {};

    function alreadyShown(id, channel) {
        return localStorage.getItem(storagePrefix + channel + '-' + id) === '1';
    }

    function markShown(id, channel) {
        localStorage.setItem(storagePrefix + channel + '-' + id, '1');
    }

    function ensureContainer() {
        var container = document.getElementById('automation-home-notifications');
        if (!container) {
            container = document.createElement('div');
            container.id = 'automation-home-notifications';
            container.setAttribute('aria-live', 'assertive');
            document.body.appendChild(container);
        }
        return container;
    }

    function showHome(item) {
        if (!item.home || alreadyShown(item.id, 'home')) { return; }
        markShown(item.id, 'home');
        var card = document.createElement('div');
        card.className = 'automation-home-notification severity-' + item.severity;
        var title = document.createElement('strong');
        title.textContent = item.title;
        var message = document.createElement('span');
        message.textContent = item.message;
        var close = document.createElement('button');
        close.type = 'button';
        close.textContent = '\u00d7';
        close.addEventListener('click', function () { card.remove(); });
        card.appendChild(title);
        card.appendChild(message);
        card.appendChild(close);
        ensureContainer().appendChild(card);
    }

    function serviceWorkerNotification(title, options) {
        if (!('serviceWorker' in navigator)) {
            return Promise.reject(new Error('service_worker_unavailable'));
        }
        return navigator.serviceWorker.register(
            '/plugins/automation_rules/static/browser_sw.js?v=1.0.6'
        ).then(function (registration) {
            return registration.showNotification(title, options);
        });
    }

    function deliverBrowser(title, message, tag) {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            return Promise.reject(new Error('notification_permission_missing'));
        }
        return serviceWorkerNotification(title, {body: message, tag: tag})
            .catch(function () {
                var notification = new Notification(title, {body: message, tag: tag});
                notification.onclick = function () { window.focus(); notification.close(); };
            });
    }

    function showBrowser(item) {
        if (!item.browser || alreadyShown(item.id, 'browser') || pending[item.id]) { return; }
        pending[item.id] = true;
        deliverBrowser(item.title, item.message, item.id).then(function () {
            markShown(item.id, 'browser');
            delete pending[item.id];
        }).catch(function (error) {
            delete pending[item.id];
            var result = document.getElementById('automation-browser-permission-result');
            if (result && window.automationRuleText) {
                result.textContent = window.automationRuleText.permissionDeliveryFailed +
                    ' (' + (error.name || 'Error') + ')';
            }
        });
    }

    function poll() {
        fetch(endpoint, {credentials: 'same-origin', cache: 'no-store'})
            .then(function (response) {
                if (!response.ok) { throw new Error('notification_http_error'); }
                return response.json();
            })
            .then(function (payload) {
                (payload.notifications || []).slice().reverse().forEach(function (item) {
                    if (window.location.pathname === '/') { showHome(item); }
                    showBrowser(item);
                });
            })
            .catch(function () {});
    }

    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = '/plugins/automation_rules/static/automation_rules.css?v=1.0.6';
    document.head.appendChild(css);
    window.setTimeout(poll, 1500);
    window.setInterval(poll, 15000);
}());
