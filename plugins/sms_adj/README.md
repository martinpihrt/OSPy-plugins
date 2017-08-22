SMS Settings Readme
====

Control your sprinkler using SMS (Short Message Service).  
For this plugin is needed to SMS modem with the telephone service provider.  
This plugin needs Gammu. If not installed Gammu and Python-Gammu, plugin installs Gammu and Python-Gammu in to the system himself.  
On first use (if run installation gammu) please wait for status.  
Reports shall be transmitted only on the phone number of administrator who sent the order (to other phone numbers plugin unresponsive and SMS messages deletes).

Plugin setup
-----------
* Check Use SMS modem:  
  If checked use SMS modem plugin is enabled.  

* Check Signal strength in the status window:  
  If checked use Signal strength in the status window in list is information about the signal strength.    

* Number 1:  
  Type 1 telephone number for 1 administrator in format +xxxyyyyyyyyy.

* Number 2:  
  Type 2 telephone number for 2 administrator in format +xxxyyyyyyyyy.

* Command for info:
  Type command for send two SMS with system information (default command is "info"). 

* Command for stop irrigation:
  Type command for stop irrigation (disabled sheduller).  
  (default command is "start").

* Command for start irrigation:
  Type command for start irrigation (enabled sheduller).  
  (default command is "stop").

* Command for reboot system:
  Type command for reboot system (hard reboot system - not OSPy service).  
  (default command is "reboot").

* Command for poweroff system:
  Type command for poweroff system (hard shutdown system - not stop OSPy service).  
  (default command is "poweroff").

* Command for update OSPi from GITHUB:
  Type command for update OSPy from GITHUB.  
  (default command is "update").

* Command for send foto from webcam:
  Type command for send foto from webcam.    
  For this function required e-mail and webcam plugin with all function setup. E-mail with photo attachments from USB webcam.  
  (default command is "foto").

* Command for help:
  Type command for help. Send SMS with all available commands.  
  (default command is "help").

* Command for run now program:
  Type command for run now program xx number.  
  (default command is "run").  
  (Example: run1 = run now program 1 if exists)
  

* Status:
  Status window from the plugin.  

Visit [Martin Pihrt's blog](http://www.pihrt.com/elektronika/259-moje-rapsberry-pi-sms-ovladani-rpi). for more information.
