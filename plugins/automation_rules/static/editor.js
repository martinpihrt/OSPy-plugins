(function () {
    'use strict';

    function uniqueOptions(items, valueKey, labelKey) {
        var found = {};
        items.forEach(function (item) {
            var value = item[valueKey];
            if (value && !found[value]) {
                found[value] = {value: value, label: item[labelKey] || value};
            }
        });
        return Object.keys(found).sort().map(function (key) { return found[key]; });
    }

    function addOption(select, value, label, selected) {
        var option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        option.selected = value === selected;
        select.appendChild(option);
    }

    function fillSelect(select, options, selected) {
        select.innerHTML = '';
        addOption(select, '', window.automationRuleText.choose, !selected);
        options.forEach(function (item) {
            addOption(select, item.value, item.label, selected);
        });
        if (selected && !options.some(function (item) { return item.value === selected; })) {
            addOption(select, selected, selected, selected);
        }
    }

    function catalogFor(row) {
        return window.automationRuleCatalog || [];
    }

    function fillProviders(row) {
        var selected = row.dataset.provider || '';
        fillSelect(row.querySelector('.provider-select'),
            uniqueOptions(catalogFor(row), 'provider_id', 'provider_label'), selected);
        fillResources(row);
    }

    function fillResources(row) {
        var provider = row.querySelector('.provider-select').value;
        var selected = row.dataset.resource || '';
        fillSelect(row.querySelector('.resource-select'), uniqueOptions(catalogFor(row)
            .filter(function (item) { return item.provider_id === provider; }),
            'resource_id', 'resource_label'), selected);
        fillValues(row);
    }

    function fillValues(row) {
        var provider = row.querySelector('.provider-select').value;
        var resource = row.querySelector('.resource-select').value;
        var selected = row.dataset.value || '';
        fillSelect(row.querySelector('.value-select'), uniqueOptions(catalogFor(row)
            .filter(function (item) {
                return item.provider_id === provider && item.resource_id === resource;
            }), 'value_id', 'value_label'), selected);
        updateValue(row);
    }

    function updateValue(row) {
        var provider = row.querySelector('.provider-select').value;
        var resource = row.querySelector('.resource-select').value;
        var value = row.querySelector('.value-select').value;
        var definition = catalogFor(row).find(function (item) {
            return item.provider_id === provider && item.resource_id === resource && item.value_id === value;
        });
        row.querySelector('.condition-unit').textContent = definition ? definition.unit : '';
        updateOperator(row);
    }

    function updateOperator(row) {
        var operator = row.querySelector('.operator-select').value;
        var expected = row.querySelector('.expected-input');
        var booleanOperator = operator === 'is_true' || operator === 'is_false';
        var rangeOperator = operator === 'between' || operator === 'not_between';
        expected.disabled = booleanOperator;
        expected.placeholder = rangeOperator ? window.automationRuleText.rangeExample : '';
        row.querySelector('.expected-label').classList.toggle('boolean-condition', booleanOperator);
    }

    function bindRow(row) {
        row.querySelector('.provider-select').addEventListener('change', function () {
            row.dataset.provider = this.value;
            row.dataset.resource = '';
            row.dataset.value = '';
            fillResources(row);
        });
        row.querySelector('.resource-select').addEventListener('change', function () {
            row.dataset.resource = this.value;
            row.dataset.value = '';
            fillValues(row);
        });
        row.querySelector('.value-select').addEventListener('change', function () {
            row.dataset.value = this.value;
            updateValue(row);
        });
        row.querySelector('.operator-select').addEventListener('change', function () {
            updateOperator(row);
        });
        row.querySelector('.remove-condition').addEventListener('click', function () {
            var list = row.closest('.condition-list');
            if (list.querySelectorAll('.condition-row').length > 1) {
                row.remove();
                renumber(row.closest('form'));
            }
        });
        fillProviders(row);
    }

    function renumber(form) {
        var rows = form.querySelectorAll('.condition-row');
        rows.forEach(function (row, index) {
            row.querySelector('.condition-number').textContent = (index + 1) + '.';
            row.querySelector('.condition-id').name = 'condition_id_' + index;
            row.querySelector('.provider-select').name = 'provider_id_' + index;
            row.querySelector('.resource-select').name = 'resource_id_' + index;
            row.querySelector('.value-select').name = 'value_id_' + index;
            row.querySelector('.operator-select').name = 'operator_' + index;
            row.querySelector('.expected-input').name = 'expected_' + index;
        });
        form.querySelector('.condition-count').value = rows.length;
    }

    function addCondition(form) {
        var list = form.querySelector('.condition-list');
        if (list.querySelectorAll('.condition-row').length >= 20) { return; }
        var row = list.querySelector('.condition-row').cloneNode(true);
        row.dataset.provider = '';
        row.dataset.resource = '';
        row.dataset.value = '';
        row.querySelector('.condition-id').value = '';
        row.querySelector('.expected-input').value = '0';
        row.querySelector('.operator-select').value = 'lte';
        list.appendChild(row);
        bindRow(row);
        renumber(form);
    }

    function browserPermission() {
        var result = document.getElementById('automation-browser-permission-result');
        if (!('Notification' in window)) {
            result.textContent = window.automationRuleText.permissionDenied;
            return;
        }
        Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                result.textContent = window.automationRuleText.permissionDenied;
                return;
            }
            function directNotification() {
                var notification = new Notification(
                    window.automationRuleText.browserTestTitle,
                    {body: window.automationRuleText.browserTestMessage,
                     tag: 'automation-browser-permission-test'});
                notification.onclick = function () {
                    window.focus();
                    notification.close();
                };
            }
            var delivery = ('serviceWorker' in navigator) ?
                navigator.serviceWorker.register(
                    '/plugins/automation_rules/static/browser_sw.js?v=1.0.7'
                ).then(function (registration) {
                    return registration.showNotification(
                        window.automationRuleText.browserTestTitle,
                        {body: window.automationRuleText.browserTestMessage,
                         tag: 'automation-browser-permission-test'});
                }).catch(directNotification) : Promise.resolve().then(directNotification);
            delivery.then(function () {
                result.textContent = window.automationRuleText.permissionGranted;
            }).catch(function (error) {
                result.textContent = window.automationRuleText.permissionDeliveryFailed +
                    ' (' + (error.name || 'Error') + ')';
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.automation-rule-form').forEach(function (form) {
            form.querySelectorAll('.condition-row').forEach(bindRow);
            form.querySelector('.add-condition').addEventListener('click', function () {
                addCondition(form);
            });
            form.addEventListener('submit', function () { renumber(form); });
        });
        var permission = document.getElementById('automation-browser-permission');
        if (permission) { permission.addEventListener('click', browserPermission); }
    });
}());
