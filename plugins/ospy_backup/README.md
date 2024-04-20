OSPy Backup Readme
====

Tested in Python 3+

This extension creates a backup of data directories from all available installed extensions in OSPy. Example: "Air Temperature and Humidity Monitor/data". Local records from plugins (for example json files with temperature, etc...) are most often found in the plugins data directories. Backups can be downloaded to our computer (phone) and possibly uploaded back to data directories in specific plugins after unpacking. Backups are in zip format (example: 20240417-201606-PluginsBackup.zip. If possible, store all records from the plugins on to your own database storage (MySQL) instead of in local "data" directories. Not only does this save the Raspberry Pi SD card, but in the event of an OSPy crash, we won't lose the saved data (since it's outside of OSPy in the database). To connect to the database, we can use an extension called: database_connector. Which will ensure the storage of data from our plugins.