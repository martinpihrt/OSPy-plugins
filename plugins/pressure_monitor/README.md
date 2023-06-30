Pressure Monitor Readme
====

Tested in Python 3+

This plugin checked pressure in pipe, if master station is switched on must be activated pressure sensor.  
If is not sensor activated in a certain time, switches off all station  and sends E-mail with error. Prevent safety for master station pump.  


Plugin setup
-----------
* Check Use pressure sensor for master station:  
  If checked use pressure sensor for master station plugin is enabled.  
  Pressure sensor is connected between GPIO 18 - pin 12 and ground.  

* Check Use Normally open:  
  If checked normally open sensor without pressure has contact open.  

* Max time to activate pressure sensor:  
  Type maximum certain time to activate pressure in pipe. Maximum time is 999 seconds.  

* Stop this run stations in scheduler:    
  Stoping these stations if no pressure in pipe. Selector for stop stations in scheduler  

* Check Send email with error:
  If checked send E-mail with error E-mail notification plugin sends E-mail with error.  
  For this function required E-mail notification plugin with all setup in plugin.   

* Select filter for graph history  
  Without limits  
  Day filter  
  Month filter  
  Year filter      

* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:  
<a href="/plugins/pressure_monitor/static/images/schematics.png"><img src="/plugins/pressure_monitor/static/images/schematics.png" width="100%"></a>  

Recommend using optocoupler between GPIO and sensor. Visit [Martin Pihrt's blog](http://www.pihrt.com/elektronika/248-moje-rapsberry-pi-zavlazovani-zahrady). for more information.
