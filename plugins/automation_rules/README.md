# Automation Rules

Automation Rules is a graphical, optional consumer of OSPy's read-only `ospy.provider.v1` monitoring contract. A rule is displayed as one main card. Its conditions are rows on a desktop and responsive subcards on a narrow screen. Rules can require every condition (`AND`) or at least one condition (`OR`).

Each condition selects a running provider, resource, value, comparison and limit. Values and canonical units come from the provider declaration, so the editor does not invent units or perform an extra GPIO/I2C measurement. Missing, stale, disabled or erroneous providers never satisfy a condition and never silently clear an already active incident.

The built-in **OSPy Sensors** provider also lists every enabled OSPy sensor by its configured name, independently of whether it is a Pihrt or Shelly device. It exposes the selected temperature, contact, motion, moisture, flow, output, power, voltage, humidity or illuminance reading. Pihrt multi-contact and soil devices expose each input separately. An ultrasonic tank sensor exposes its raw distance plus derived water level, fill percentage and configured volume. The adapter reads only the last cached sensor values and never polls hardware.

The built-in **Date and time** provider exposes the current local ISO date, 24-hour time, weekday, month and day of month. Conditions support **in range** and **outside range** comparisons written as `start..end`, for example `2026-05-01..2026-09-30` or `08:00..18:00`. Reversed time ranges such as `22:00..06:00` cross midnight, allowing one time condition to be combined with sensor limits through `AND`.

The built-in **OSPy status** provider exposes the scheduler state, manual and scheduled modes, user water-level adjustment, remaining rain-delay seconds, rain-sensor configuration and activity, cached OSPy update availability, cached plug-in update availability and the known plug-in update count. It only reads current local and cached state; evaluating a rule does not start an update check or network request.

Rules support a confirmation duration, repeated-notification interval, recovery notification, severity and these notification channels:

- an OSPy Home popup;
- a browser notification after explicit browser permission;
- E-mail Notifications SSL or E-mail Notifications;
- Telegram Bot authorized chats;
- OSPy Mobile API push notifications.

Test mode is enabled by default. It evaluates rules and records the decisions in a bounded history but does not enqueue local notifications or send anything to external recipients. Test state is separate from live state, so testing cannot consume a later live trigger. The **Test saved rule** action also never sends.

Browser notifications require an open OSPy page and permission granted through the settings button. Granting permission immediately sends a browser test; a Service Worker fallback covers browsers that reject the direct Notification constructor. Mobile push remains the channel for delivery while the web interface is closed. Every live notification includes the evaluated value, operator and configured limit. Notification history stores rule decisions and delivery status, not credentials or complete provider snapshots.

Automation Rules does not stop stations or execute control/safety actions. Existing monitoring and notification plug-ins remain independently usable.

Version 1.0.7 adds the built-in OSPy status source, keeps general settings on one readable desktop row and makes saved rule cards collapsible. Rule headers now distinguish Disabled, Ready and Triggered states without presenting the status as a red action button. Version 1.0.6 prioritizes Service Worker notification delivery for Firefox and reports client delivery errors on the settings page instead of ignoring them. Version 1.0.5 adds local date/time range conditions, detailed notification messages and verifiable browser delivery with a Service Worker fallback. Version 1.0.4 adds enabled Pihrt and Shelly OSPy sensors as rule sources while preserving the read-only provider model. Version 1.0.3 displays every Boolean setting and notification channel as the same red/green sliding switch used by other OSPy plug-ins. Hovering over form fields, selectors, switches and action buttons shows a short localized description of the control. General switches are kept directly beside their labels. An explicit confirmed notification test bypasses conditions and timing, sends one real message through the channels currently selected in the rule and records each delivery result without changing incident state. Browser notifications are polled on every authenticated OSPy page. Home popup cards remain restricted to the Home page and are not consumed while the user is viewing another page. Mobile push uses the dedicated `automation` category when supported by OSPy and includes the stable rule ID, rule name and event in structured notification data. Older OSPy releases continue to classify the same event as `other`.
