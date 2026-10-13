Database Connector Readme
====

Tested in Python 3+
This extension uses a database connection via the interface: mysql-connector-python to install use: sudo pip install mysql-connector-python.
https://dev.mysql.com/doc/connector-python/en/connector-python-installation.html

The plug-in includes an OSPy `plugin.json` manifest and implements the common lifecycle and `health()` interfaces. Diagnostics reports whether the connector is enabled and available, its version, configured server and database, and the result of the latest real database operation. Database connections and cursors are closed after every operation.

October 13, 2026 GitHub/OSPy-plugins/plugins/database_connector — The durable SQLite-backed queue now preserves the source-command timestamp when it replays a statement. For MySQL/MariaDB statements that use `CURRENT_TIMESTAMP` or a `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` column, the restored record therefore retains the original logging time instead of the later recovery time. The queue has an adjustable warning threshold (80 MiB by default), a hard maximum (100 MiB by default), an optional alert through E-mail Notifications SSL and an editable alert subject.

Plugin setup
-----------

* Use plugin:  
  If checked enabled plugin is enabled. When the box is checked, the extension will be active. After filling in all the fields, ospy must be restarted!

* Use buffer:
  When enabled, database commands are saved in a local SQLite queue and processed in order. If the database connection is unavailable, commands remain queued and are saved after the connection is restored. The queue records the time that the original database command was submitted; during replay the connector sets the MySQL/MariaDB session timestamp to that saved value, so `CURRENT_TIMESTAMP` and timestamp defaults keep the original logging time. The queue survives OSPy restarts. The page displays its command count and used size, and lets the administrator clear it manually. Clearing permanently discards every queued command. Disabling the buffer stops background replay and sends new commands through the direct database path.

* Queue warning size and maximum size:
  The warning threshold defaults to 80 MiB and the maximum defaults to 100 MiB. Both values are adjustable, and the warning must be smaller than the maximum. The connector sends one alert after crossing the warning threshold and re-arms it after the queue shrinks below the threshold. It does not evict older records: when a new command would exceed the maximum, it is rejected and a separate one-time limit alert is sent. This protects the SD card while retaining the oldest pending records in FIFO order.

* Send queue alert e-mail through SSL and Queue alert e-mail subject:
  Enable this only when the E-mail Notifications SSL plug-in is configured. Queue alerts use that plug-in's SMTP-over-SSL settings and recipients; this plug-in stores no SMTP password. The configured subject is used as the prefix for both the warning and maximum-size messages.

* Host:  
  IP address to the database server.

* Username:  
  The login name to log in to the database.  

* Password:  
  The login password to log in to the database.

* Port:  
  Port for connecting to the database server. The default is usually 3306.

* Database name:  
  The name of the database in which there will be tables with measured data. To be able to connect multiple ospy systems to one database server. Each ospy will have its own database (example: ospy_1, ospy_2...

* Connection test:  
  After pressing the test button, this extension will try to connect to the database.

* Status:  
  Status window from the plugin.
