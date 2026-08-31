# Irrigation Safety

Irrigation Safety is a dedicated protection layer for OSPy. It combines live OSPy output state with cached `ospy.provider.v1` data and never performs an extra hardware read.

Version 1.0.0 provides:

- Off, Monitor only and Active protection modes. Monitor only is the safe commissioning mode.
- A separate flow profile for every enabled non-master OSPy station, including startup delay and fault-confirmation time.
- Combined expected ranges when several fully configured stations run at once.
- Detection of no, low or high flow during irrigation and flow while no irrigation station is active.
- Optional pressure and tank-level protection, including unavailable or stale measurement incidents.
- One-shot automatic learning from Water Meter. Learning accepts samples only after startup delay and while exactly one selected station is active. A robust P10/P90 range expanded by a configurable margin is saved when enough samples have been collected.
- Guarded shutdown that clears current runs and outputs, switches off the separate master relay and optionally disables the scheduler.
- Persistent incident locking. A locked incident is enforced continuously and can be acknowledged only after its condition is no longer active. The scheduler is never re-enabled automatically.
- A bounded temporary bypass that suppresses control actions while monitoring, incident history and notifications continue.
- E-mail delivery through either official e-mail plug-in and immediate mobile push through OSPy's asynchronous push dispatcher. Notification work is kept outside the safety evaluation worker.
- A responsive page styled after Thermostat and Automation Rules, using OSPy buttons and slider switches. Current values, active stations, learning progress, incidents and history update every two seconds without refreshing the page.
- Health, mobile-card and read-only `ospy.provider.v1` contributions.

## Safety workflow

1. Install and enable Water Meter.
2. Select **Monitor only**.
3. Enable a station profile and either enter verified flow limits or start automatic learning, then run that station by itself.
4. Test every configured station and notification channel.
5. Select **Active protection** only after the displayed limits and startup delays have been verified on the actual irrigation hardware.

If a confirmed fault occurs in Active protection, output shutdown is executed before e-mail or push delivery. A notification outage therefore cannot delay valve or pump shutdown.
