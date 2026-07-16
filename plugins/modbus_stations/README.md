Modbus Stations Readme
====

Tested in Python 3

This plugin can be used to control devices via modbus protocol (8ch relay boards).
Requires to be installed in to the Linux system. Use: sudo apt install python3-serial and restart ospy!

The plug-in includes an OSPy `plugin.json` manifest and implements the common
lifecycle and `health()` interfaces. Its former one-shot thread was replaced by
explicit registration and removal of the three station signal receivers, which
prevents duplicate Modbus commands after a plug-in restart. Diagnostics reports
pyserial availability, non-secret serial settings, receiver count, and the
latest successful command or communication error. Serial handles are closed
after every station command.

Plugin setup
-----------

* Check Use Control:  
  If checked enabled plugin is enabled. 

* Check Enable logging:  
  If checked enabled logging is enabled.

* Number of relay boards:
  Enter how many relay boards are used (each board has 8 relay outputs). Ex: 2 means 16 outputs and 2 boards.

* Serial port:
  Specify which port will be used for communication. Use the "system information" plugin to find the port. Example: /dev/ttyUSB0

* Communication speed:
  Enter the speed at which the connected modules communicate. Example: 4800, 9600, 19200, 38400, 57600, 115200, 128000, 256000 (in Baud).

* Status:  
  Status window from the plugin.  

