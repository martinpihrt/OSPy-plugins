(function () {
    "use strict";

    function text(id, value) {
        var element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    function cell(row, value, className) {
        var item = document.createElement("td");
        item.textContent = value == null ? "" : String(value);
        if (className) item.className = className;
        row.appendChild(item);
    }

    function renderRows(targetId, values, renderer, emptyText, columns) {
        var body = document.getElementById(targetId);
        if (!body) return;
        body.textContent = "";
        if (!values || !values.length) {
            var emptyRow = document.createElement("tr");
            var emptyCell = document.createElement("td");
            emptyCell.colSpan = columns;
            emptyCell.textContent = emptyText;
            emptyRow.appendChild(emptyCell);
            body.appendChild(emptyRow);
            return;
        }
        values.forEach(function (value) { body.appendChild(renderer(value)); });
    }

    function render(status) {
        var cfg = window.irrigationSafetyConfig;
        text("safetyMode", status.mode_label || "---");
        text("safetyFlow", status.flow_lpm == null ? cfg.texts.unavailable : Number(status.flow_lpm).toFixed(2) + " L/min");
        text("safetyExpected", status.expected_minimum == null || status.expected_maximum == null ? cfg.texts.unavailable : Number(status.expected_minimum).toFixed(2) + "–" + Number(status.expected_maximum).toFixed(2) + " L/min");
        text("safetyStations", status.active_stations && status.active_stations.length ? status.active_stations.join(", ") : cfg.texts.none);
        text("safetyIncidents", status.active_incidents + " / " + status.locked_incidents);
        text("safetyBypass", status.bypass ? new Date(status.bypass_until * 1000).toLocaleString() : cfg.texts.none);

        Object.keys(status.learning || {}).forEach(function (stationId) {
            var learning = status.learning[stationId];
            if (learning.active) text("learningStatus-" + stationId, learning.samples + " / " + learning.required);
        });

        renderRows("safetyIncidentRows", status.incidents, function (incident) {
            var row = document.createElement("tr");
            cell(row, new Date(incident.opened_at * 1000).toLocaleString());
            cell(row, incident.label + (incident.detail ? " — " + incident.detail : ""));
            var state = incident.condition_active ? cfg.texts.active : cfg.texts.cleared;
            if (incident.latched) state += " / " + cfg.texts.locked;
            cell(row, state, incident.condition_active ? "safetyStateActive" : (incident.latched ? "safetyStateLocked" : "safetyStateCleared"));
            cell(row, incident.action || "");
            return row;
        }, cfg.texts.none, 4);

        renderRows("safetyHistoryRows", status.history, function (record) {
            var row = document.createElement("tr");
            cell(row, record.datetime || new Date(record.timestamp * 1000).toLocaleString());
            cell(row, record.label || record.event_label || "");
            cell(row, record.detail || "");
            cell(row, record.action || "");
            return row;
        }, cfg.texts.none, 4);
    }

    function poll() {
        var cfg = window.irrigationSafetyConfig;
        fetch(cfg.statusUrl, {credentials: "same-origin", cache: "no-store"})
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (status) {
                var error = document.getElementById("safetyLiveError");
                if (error) error.classList.add("safetyHidden");
                render(status);
            })
            .catch(function () {
                var error = document.getElementById("safetyLiveError");
                if (error) {
                    error.textContent = cfg.texts.pollingError;
                    error.classList.remove("safetyHidden");
                }
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        poll();
        window.setInterval(poll, 2000);
    });
}());
