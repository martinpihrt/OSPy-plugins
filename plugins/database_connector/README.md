Database Connector Readme
====

Tested in Python 3+
This extension uses a database connection via the interface: mysql-connector-python to install use: sudo pip install mysql-connector-python.
https://dev.mysql.com/doc/connector-python/en/connector-python-installation.html


Plugin setup
-----------

* Use plugin:  
  If checked enabled plugin is enabled. When the box is checked, the extension will be active. After filling in all the fields, ospy must be restarted!

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