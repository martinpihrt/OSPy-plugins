# OSPy-plugins Changelog

July 09 2026
-----------
(Martin Pihrt) - Direct 16 Relay Outputs<br/>
Hardened Direct 16 Relay Outputs runtime handling. Relay count and trigger level are normalized before use, unsupported platforms now stop GPIO processing cleanly instead of retrying every loop, station-to-relay access is bounded to the configured GPIO list, loop sleeping now responds promptly to plug-in stop, and repeated runtime errors are throttled.

(Martin Pihrt) - Relay Test<br/>
Hardened Relay Test execution. The relay pulse now runs in a short background thread instead of blocking the web request, the relay output is always forced off in a finally block, repeated starts are ignored while a test is already running, stop() also forces the relay off, and the redirect no longer gets logged as an internal error.

(Martin Pihrt) - Pulse Output Test<br/>
Hardened Pulse Output Test runtime handling. Test output and duration are clamped before use, the duration field now exposes the allowed range, the pulse loop can stop promptly through the thread stop event, and the selected output is forced back to a safe state unless an existing scheduler run still needs it active.

(Martin Pihrt) - Proto<br/>
Reduced Proto example background load. The demonstration loop now runs at a lighter interval, status messages are logged only periodically instead of every loop, repeated traceback logging is throttled, and the event window is no longer cleared repeatedly while the plug-in is running.

(Martin Pihrt) - Pressurizer<br/>
Hardened Pressurizer station selection and relay shutdown. Selected station IDs are normalized before schedule matching and rendered correctly after saving, disabled/scheduler-off messages and runtime errors are throttled, missing master-station warnings are logged once per condition, and stopping the plug-in forces the pressurizer relay signal/output off.

(Martin Pihrt) - Pressure Monitor<br/>
Reduced Pressure Monitor load and log spam. The pressure countdown is logged at a throttled interval, the web pressure polling interval is less aggressive, repeated GPIO/runtime/log/SQL/e-mail errors are throttled, selected station IDs are normalized before stopping scheduler runs, GPIO read failures return a safe inactive state, and settings render safely when the background thread is unavailable.

(Martin Pihrt) - Pool Heating<br/>
Reduced Pool Heating background load by refreshing Air Temperature plug-in probe data at a fixed interval and throttling status log rewrites. Repeated runtime/probe/e-mail errors are throttled, settings render safely when the background thread is unavailable, selected output is validated, safety e-mail now respects the Send E-mail switch, and regulation stops only station runs created by this plug-in.

(Martin Pihrt) - Ping Monitor<br/>
Reduced Ping Monitor blocking and log noise. Ping command timeout is shorter, ping and e-mail intervals are clamped to safe minimums, address availability is logged on state changes instead of every cycle, regular ping cycles no longer clear the status log, and repeated runtime/log/CSV/graph errors are throttled.

(Martin Pihrt) - Photovoltaic Boiler<br/>
Reduced Photovoltaic Boiler background load by refreshing Air Temperature plug-in probe data at a fixed interval instead of every loop and by throttling status log rewrites. Repeated runtime/probe errors are now throttled, the settings page works even when the background thread is not available, selected output is validated, and stopping the plug-in only deactivates a station run created by this plug-in.

(Martin Pihrt) - OSPy package Backup<br/>
Hardened backup file handling. Backup creation now prepares missing data/temp/archive folders before creating the zip, the Backup now action includes a CSRF token, and delete/download requests validate the selected backup index and resolved file path before touching files.

(Martin Pihrt) - Network Ping Monitor<br/>
Reduced Network Ping Monitor log and retry noise. Disabled monitoring now writes its status only once instead of every loop, summary and log intervals are clamped to safe minimums, repeated runtime/local-log/SQL-log errors are throttled, and server definitions are rebuilt immediately after saving settings even when the background thread is not currently running.

(Martin Pihrt) - Home Assistant<br/>
Hardened MQTT Home Assistant broker handling. Broker connection attempts now use a shorter timeout and reconnect backoff, publish failures and repeated loop errors are throttled, MQTT payload decoding is tolerant of invalid UTF-8, stopping the plug-in handles missing discovery devices cleanly, settings JSON masks the broker password, and dependency hints now use fixed apt packages instead of pip.

(Martin Pihrt) - MQTT<br/>
Hardened the base MQTT plug-in. Missing paho-mqtt no longer triggers an automatic pip install; settings now show an Install libraries button that installs the fixed apt package python3-paho-mqtt. MQTT broker connection attempts use a shorter timeout and reconnect backoff, publish failures and repeated errors are throttled, the client is stopped more cleanly, the settings JSON output no longer exposes the broker password, and the password field can now be shown or hidden from the settings page.

(Martin Pihrt) - Modbus Stations<br/>
Reduced Modbus Stations blocking during RS485/USB failures by using shorter serial timeouts, throttled serial error logging and a shared serial write lock. The command log is now bounded to the latest entries, missing log files no longer create traceback noise, and address/firmware reads handle short responses without crashing.

(Martin Pihrt) - E-mail Reader<br/>
Added IMAP connection timeouts, a minimum mail check interval, safer logout handling and throttled error logging. Missing sender/folder results now return an empty message list instead of causing follow-up loop errors, reducing load and log spam when the mail server or account settings are unavailable.

(Martin Pihrt) - E-mail Notifications<br/>
Added an SMTP connection timeout and reduced retry load when the mail server is unavailable. The unsent e-mail queue now backs off repeated failed sends instead of retrying at a fixed short interval, and SMTP connections are closed reliably after send attempts.

(Martin Pihrt) - Door Opening<br/>
Audited Door Opening. The plug-in does not run a background loop; opening is started only from the web form. Added validation for selected output and open time, prevented duplicate Door Opening runs on the same output, refreshed footer data after settings changes, and cleared the one-shot sender thread after it finishes.

(Martin Pihrt) - System Information<br/>
Verified that System Information does not run a background thread. Reduced page-open I2C load by scanning the bus once at low priority and reusing the detected address list for plug-in hardware hints instead of probing the same addresses repeatedly.

(Martin Pihrt) - Weather-based Water Level<br/>
Reduced Weather-based Water Level recalculation load by separating normal weather callbacks from forced settings updates. Weather callbacks no longer trigger a full recalculation more often than the hourly calculation interval, calculation errors retry with backoff and throttled logging, and freeze protection now skips cleanly when current temperature data is unavailable.

(Martin Pihrt) - UPS Monitor<br/>
Reduced UPS Monitor status/log load during power failures. The live shutdown countdown is now returned through the JSON status used by the settings page, while the plug-in log is updated only on countdown milestones instead of every loop. The power-restored notification is sent only after a real previous fault.

(Martin Pihrt) - Astro Sunrise and Sunset<br/>
Reduced Astro Sunrise and Sunset background load by calculating sunrise/sunset less often while keeping the one-second program start check. Astral import/calculation errors are now logged with throttling, failed calculations back off before retrying, and the plug-in no longer attempts an automatic pip install on externally managed Python systems.
Added an Install libraries button when Astral is missing. The button installs the fixed apt package python3-astral and writes progress and fallback commands to the status log.

(Martin Pihrt) - Database Connector<br/>
Added a database connection timeout, current settings are now used for each connection attempt, and database cursors/connections are closed reliably after queries. Repeated database errors and routine SQL command logging are throttled so unavailable database servers do not repeatedly block or flood the plug-in log. Database backups now pass a mysqldump connect timeout and report backup timeouts cleanly.

(Martin Pihrt) - E-mail Notifications SSL<br/>
Added an SMTP connection timeout and reduced unnecessary retry load when the mail server is unavailable. The unsent e-mail queue now backs off repeated failed sends instead of retrying at a fixed short interval, and the background loop checks less aggressively while still reacting to finished runs and queued mail.

(Martin Pihrt) - Real Time and NTP time, Air Temperature and Humidity Monitor<br/>
Set Real Time RTC DS1307 I2C access to low priority and Air Temperature DS18B20 I2C reads to normal priority. This keeps time synchronization behind measurement-critical I2C traffic while temperature reads still run ahead of low-priority display updates, with compatibility for older OSPy versions that do not support explicit I2C priorities.
Shortened Real Time NTP request timeout and handled NTP network failures without traceback spam. Air Temperature DS18B20 failures now use a short backoff, fewer failed read attempts and throttled status logging, so a bad sensor or busy I2C bus does not repeatedly block the plug-in loop.

(Martin Pihrt) - Button Control<br/>
Reduced Button Control I2C load by updating MCP23017 LED outputs only when the button state changes. Button input configuration/read transactions now explicitly use normal I2C priority, keeping button presses ahead of low-priority display traffic without pre-empting high-priority wind measurements.

(Martin Pihrt) - Current Loop Tanks Monitor<br/>
Reduced Current Loop Tanks Monitor load by adding a configurable tank measurement interval and reading only tanks that are enabled or required by regulation, stop-station or e-mail rules. Status logging is now throttled so unchanged measurement state is not rewritten every cycle, and repeated browser console debug output was removed from live tank updates.

(Martin Pihrt) - CHMI<br/>
Reduced unnecessary CHMI load during radar service/network failures: failed downloads or bitmap processing errors now wait for the normal 10-minute update interval instead of retrying almost immediately. Radar HTTP requests now reuse one session for downloads and hardware map posts.

(Martin Pihrt) - Shelly Cloud Integration<br/>
Reduced unnecessary Shelly Cloud Integrator load by reusing one HTTP session for device requests, throttling repeated status log writes, adding per-device retry backoff after HTTP/request errors, and handling bad JSON responses without raising an undefined exception. The status window now keeps only the latest written status block instead of accumulating repeated history entries.

(Martin Pihrt) - LCD Display<br/>
Changed LCD Display logging for normal low-priority I2C contention: when the bus is busy, the plug-in now logs a short throttled warning and retries later instead of filling the log with repeated tracebacks. The busy-bus detection now accepts OSError/IOError messages containing `I2C bus is busy`, so small platform differences do not fall back to traceback logging.

July 07 2026
-----------
(Martin Pihrt) - IP Cam<br/>
Refine IP Cam snapshot setup flow.

(Martin Pihrt) - LCD Display<br/>
Added a Wind Speed display switch that shows current and maximum wind speed from Wind Speed Monitor, and re-initializes the HD44780/PCF8574 LCD at the start of each display cycle without re-scanning the I2C address to recover from corrupted characters during long operation.

July 06 2026
-----------
(Martin Pihrt) - IP Cam<br/>
Changed IP Cam snapshot previews to embed cached JPG/GIF files directly in the Snapshots page instead of issuing separate preview requests, avoiding 404 preview errors, and changed the main IP Cam status image size display from bytes to KB.

(Martin Pihrt) - Label Maker<br/>
Updated Label Maker help and README dependency text after the built-in EAN13 barcode generator change. The documentation now separates QR, QR with logo and EAN13 requirements and notes that python-barcode is no longer needed. Added advanced QR settings for module size, border, error correction, foreground/background color, a configurable PNG download filename, clearer preview/download controls, and client/server-side input validation.
Stopped automatic pip installs for missing Label Maker dependencies on externally managed Python environments. The plug-in now logs apt package hints and no longer reports the normal POST redirect as an error. Added an Install libraries button to the Label Maker settings page when required system packages are missing, with installation progress shown in the status log. Replaced the EAN13 python-barcode dependency with an internal EAN13 PNG generator using Pillow, avoiding the unavailable python3-barcode package on Raspberry Pi OS Bookworm.

(Martin Pihrt) - IP Scanner<br/>
Changed the common web ports option from a checkbox to a switch-style control. Improved IP Scanner with active local network discovery, network summary, structured device table, hostname and vendor hints, Gateway/This OSPy/Sensor candidate notes, and optional checks for common web ports 80, 443, 8080 and 8081.

(Martin Pihrt) - Weather-based Water Level<br/>
Added a Forecast details page that shows the last weather calculation input and result, including history, today and forecast rows with rainfall, average temperature, wind, humidity and the resulting water level adjustment.

(Martin Pihrt) - Signaling Examples<br/>
Updated the Signaling Examples plug-in to use a single complete signal list shared by code, settings, help, and README documentation. The settings page now refreshes status automatically and shows the last received signal in a separate auto-updating field.

(Martin Pihrt) - LCD Display, Wind Speed Monitor<br/>
Improved I2C bus cooperation between LCD Display and Wind Speed Monitor: Wind Speed Monitor now requests high-priority I2C access for PCF8583 counter setup and reads, while LCD Display uses low-priority short-timeout access so display scrolling does not delay time-sensitive measurements.
LCD Display now uses HD44780 display-shift commands for scrollable text that fits into the controller DDRAM buffer, reducing I2C traffic while preserving full long-text scrolling behavior for longer messages.
