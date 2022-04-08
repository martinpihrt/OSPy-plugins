RTC (real time) and NTP time synchronization Readme
====

Not ready to use

When is enabled synchronization RTC Time and NTP time, system time adjusted every hour from NTP server (is posible) or RTC time (if exists). Time from NTP server is saved to real time DS 1307 (on I2C bus 0x68) as HW time.  

RTC Clocks:  
* DS1307, MCP79400, DS3231, PCF8563.    

Plugin setup
-----------
* Check Use real time DS1307:  
  If checked use real time plugin is enabled.  

* Check Use NTP time:  
  If checked use NTP time Time is adjusting every hour from NTP server.  

* Primary NTP server IP adress:  
  Type IP adress or name for NTP server.  
  
* Secondary NTP server IP adress:  
  Type IP adress or name for NTP server.    
  
* NTP port:  
  Type port for NTP server (default is 123).  
 
* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/real_time/static/images/schematics.png"><img src="/plugins/real_time/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/249-moje-rapsberry-pi-gpio-a-i2c-periferie). for more information.  

Note: For this plugin neaded enabled I2C bus and SMBus in system.
