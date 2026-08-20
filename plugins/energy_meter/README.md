# Energy Meter

Energy Meter is a multi-meter electricity monitor for OSPy. It is designed for Shelly Pro 3EM and Shelly 3EM-63T Gen3 devices and keeps import, export, per-phase power, prices and solar-system calculations in a persistent history.

## Connection sources

Direct LAN / IP is the default and recommended source. Enter an IP address, an optional port, or a DNS name such as `meter.local`; OSPy reads `http://HOST/rpc/Shelly.GetStatus` directly, works without Shelly Cloud or Internet access, and can use Shelly local digest authentication. The second source is the device cache of Shelly Cloud Integration. That mode requires Shelly Cloud Integration to be installed, configured, enabled and running, and the selected three-phase meter must be available in its cache.

## Multiple meters and roles

Any number of meters can be configured. Assign each meter one of these roles: Grid connection for import from and export to the public grid, Solar production for photovoltaic generation, Load / consumption for a separately measured consumer, or Auxiliary for an independent value. Direction can be inverted for a physically reversed current-transformer installation. Grid export is never labelled as solar production.

When both Grid and Solar production meters are present, the dashboard calculates house consumption as `production + grid import - grid export`, self-consumption as `production - grid export`, the self-consumption ratio and energy independence. With only a Grid meter the production value stays unavailable rather than being guessed. Battery charging and discharging are not inferred without a dedicated measurement path.

## Counters, restart and replacement

Shelly cumulative active and returned energy counters are persisted after every successful sample in an atomically replaced JSON state file. OSPy therefore resumes from the previous baseline after restart. A lower counter is treated as a reset or meter replacement: the plug-in establishes a new baseline and does not create an artificial consumption spike. The overview also provides a CSRF-protected Reset baseline / replace meter action for planned replacement or factory reset. Local interval history is appended to `history.jsonl`, avoiding a rewrite of the complete history on every sample. Existing `history.json` data is read automatically for backward compatibility.

Intervals spanning an OSPy restart are retained as one interval and period aggregation apportions their energy by overlap with the requested day, month or year. This prevents loss of cumulative energy and avoids assigning an entire restart interval to the wrong calendar period. Calendar days use the local date and time configured on the OSPy server, start at 00:00 inclusive and end at the next 00:00 exclusive. The Shelly cumulative counters are not reset at midnight.

## History, prices and tariffs

The overview and history show L1, L2, L3 and total values for import and export, live power, a selectable retained calendar day, yesterday, the current month and the current year. Every overview period displays its historically calculated cost and feed-in income. Separate responsive energy and power graphs offer 7-, 30- and 365-day views: energy includes grid import and export L1/L2/L3/total plus solar production, while power includes L1/L2/L3/total for every configured meter. History can be downloaded as CSV or permanently deleted by an administrator. Overview totals and selected-day results are calculated from that interval history, so deleting it also clears those values and they cannot be reconstructed from the retained baseline. The cumulative-counter baseline remains only to let the next sample continue without a false energy spike. Local JSON history is supported without another plug-in; SQL history and dual local-plus-SQL logging require Database Connector. Record retention is configurable and zero means unlimited. Boolean settings use the standard OSPy switches, while each tariff uses localized Monday-through-Sunday buttons to select its active days.

Set a currency, default import price and default feed-in price. Optional tariffs match weekdays and time ranges, including ranges crossing midnight, and equal start and end times define a full-day tariff. The first matching tariff is used. The tariff identifier, tariff name, currency, actual import and feed-in prices, cost and income are written to local JSON and SQL history and CSV export. Intervals crossing a tariff boundary use time-weighted prices for their applicable segments without creating artificial energy or power samples. Changing prices or currency later does not recalculate or relabel historical records. The history table displays the stored currency and both unit prices so the calculated totals can be audited. Overview monetary totals include only records using the currently configured currency because the plug-in does not perform currency conversion, while energy totals continue to include every applicable record.

## Mobile and Home

The mobile API v1 card contains today’s grid import and export, solar production and house consumption when those values are actually measurable, current power for every configured meter and bounded history. Show on Home adds a compact current-day import/export summary to the OSPy Home plug-in section.

## Data files and API

Local files are stored in the OSPy plug-in data directory as `state.json`, the backward-compatible `history.json`, and the append-only interval journal `history.jsonl`. Authenticated administrators can read `/plugins/energy_meter/status_json` for current meters and period summaries, `/plugins/energy_meter/graph_json?from=UNIX&to=UNIX` for bounded history and `/plugins/energy_meter/log_csv` for CSV export. Standard OSPy mobile plug-in discovery exposes `mobile_status()` and `mobile_cards()`.

## Diagnostics

The OSPy diagnostics page calls `health()`. It reports worker state, whether at least one configured meter is online, the last successful read, the latest error and per-meter source/status details. Connection errors are also written to the OSPy event log.
