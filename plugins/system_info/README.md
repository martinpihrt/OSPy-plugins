System Information Readme
====

Tested in Python 3+

This plugin prints all available system information.  

The plug-in includes an OSPy `plugin.json` manifest and implements `health()`.
Diagnostics reports whether the optional I2C, `lsusb`, and process-list data
sources are available. Missing optional sources do not prevent the main system
information page from opening.


