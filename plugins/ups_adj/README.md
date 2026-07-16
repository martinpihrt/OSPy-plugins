UPS Monitor Readme
====

Tested in Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, power-line
input, shutdown countdown and delay, latest check and errors through the OSPy
system health interface. The UPS shutdown output is returned low when the
plug-in stops.

UPS Uninterruptible Power Supply (Source)
This plugin checked power line for system.  
If is error with power line in a certain time, sends plugin email with error and shutdown system (and generate pulse to GPIO for shutdown Your UPS).</p>


Plugin setup
-----------
* Check Use UPS:  
  If checked use UPS plugin is enabled.  

* Check Send email with error:  
  If checked send email with error e-mail notification plugin sends e-mail with error.    
  For this function required e-mail notification plugin with all setup in plugin.  

* Max time for shutdown countdown:  
  Type maximum certain time to shutdown system and UPS. Maximum time is 999 minutes.  

* Power line state:  
  Actual state on the Power line.

* Status:  
  Status window from the plugin.  

* Enable local logging:  
  Enable logging and graphing.

* Check Enable SQL logging:  
  If checked enabled logging save measure value to SQL database. This option requires the Database Connector extension to be installed and configured. The button will delete the upsmonitor table from the database, thus deleting all saved data from this extension! This promotion is non-refundable!   

* Graph history  
  Use quick ranges (Today, 24 h, 7 days, 30 days, All) or set a custom From/To range. The graph refreshes without reloading the settings page.     

Power line is connected via optocoupler between GPIO 23 - pin 16 and ground.
Output pulse on GPIO 24 - pin 18 (via optocoupler open colector and ground) to UPS for shutdown battery in UPS.  


The hardware should be connected as follows:  
<a href="/plugins/ups_adj/static/images/schematics.png"><img src="/plugins/ups_adj/static/images/schematics.png" width="100%"></a>

Recommend using optocoupler between GPIO and UPS. Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-rapsberry-pi-zavlazovani-zahrady). for more information.
