System Watchdog Readme  
====  

This plugin enable or disable HW Watchdog daemon in OSPy system. On the Raspberry Pi is hardware watchdog - Broadcom BCM2708 chip. This can be very useful if your Raspberry Pi is located remotely and locks up. However, this would not the preferred method of restarting the unit and in extreme cases this can result in file-system damage that could prevent the Raspberry Pi from booting. If this occurs regularly you better find the root cause of the problem rather than fight the symptoms.
The watchdog daemon will send /dev/watchdog a heartbeat every 4 seconds. If /dev/watchdog does not receive this signal it will brute-force restart your Raspberry Pi.  
This plugin needs Watchdog. If not installed Watchdog, plugin installs Watchdog in to the system himself.    

Plugin automatic installation setup:
-----------

Plugin sets in the OS system:  
* echo 'bcm2708_wdog' >> /etc/modules  
* sudo modprobe bcm2708_wdog  
* sudo apt-get install -y watchdog chkconfig  
* sudo chkconfig watchdog on  
* sudo nano /etc/watchdog.conf  
* Saving config in to file: /etc/watchdog.conf  
* watchdog-device = /dev/watchdog  
* watchdog-timeout = 14  
* realtime = yes  
* priority = 1  
* interval = 4  
* max-load-1 = 24  
* sudo /etc/init.d/watchdog start  


Options (/etc/watchdog.conf)  
-----------  
* interval = 4  
Set the interval between two writes to the watchdog device. The kernel drivers expects a write command every minute. Otherwise the system will be rebooted. Default value is 4 seconds. An interval of more than a minute can only be used with the -f command-line option.  

* max-load-1 = 24  
Set the maximal allowed load average for a 1 minute span. Once this load average is reached the system is rebooted. Default value is 0. That means the load average check is disabled. Be careful not to this parameter too low. To set a value less then the predefined minimal value of 2, you have to use the -f commandline option.  

* watchdog-device = /dev/watchdog  
Set the watchdog device name. Default is to disable keep alive support. 

* realtime = yes  
If set to yes watchdog will lock itself into memory so it is never swapped out.  

* priority = 1  
Set the schedule priority for realtime mode.  

Watchdog daemon  
-----------  

For test type in command (ex: via Putty):  
: (){ :|:& };:
