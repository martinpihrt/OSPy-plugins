(function () {
    'use strict';
    var endpoint = '/plugins/automation_rules/notifications_json';
    var storagePrefix = 'ospy-automation-notification-';

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

    function showBrowser(item) {
        if (!item.browser || alreadyShown(item.id, 'browser')) { return; }
        if (!('Notification' in window) || Notification.permission !== 'granted') { return; }
        markShown(item.id, 'browser');
        new Notification(item.title, {body: item.message, tag: item.id});
    }

    function poll() {
        if (window.location.pathname !== '/') { return; }
        fetch(endpoint, {credentials: 'same-origin', cache: 'no-store'})
            .then(function (response) {
                if (!response.ok) { throw new Error('notification_http_error'); }
                return response.json();
            })
            .then(function (payload) {
                (payload.notifications || []).slice().reverse().forEach(function (item) {
                    showHome(item);
                    showBrowser(item);
                });
            })
            .catch(function () {});
    }

    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = '/plugins/automation_rules/static/automation_rules.css?v=1.0.2';
    document.head.appendChild(css);
    window.setTimeout(poll, 1500);
    window.setInterval(poll, 15000);
}());
