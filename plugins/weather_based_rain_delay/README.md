Weather-based Rain Delay Readme
====
Updated version
-----------

Added NetAtmo support - read data from NetAtmo API of Rain module.  

Used API of [Philippe Larduinat](https://github.com/philippelt/netatmo-api-python). Not necessary to install it, is included in plug-in.  

Added options:

* Use NetAtmo:  
  Used history data of rain level from Netatmo module, must be filled all rest field.  

* NetAtmo Client ID:  
  Client ID after registration on [NetAtmo](https://dev.netatmo.com).  

* NetAtmo Client Secret:  
  Secret key for ID.  

* NetAtmo User Name:  
  Username of NetAtmo portal.  

* Netatmo Password:  
  Password of NetAtmo portal.  

* NetAtmo MAC:  
  Mac address of NetAtmo Weather Station - Main module (Indoor).  

* NetAtmo Rain MAC:  
  Mac address of Rain module, it is extracted from serial nr.  
  Example (serial nr. k123456 05:00:00:12:34:56)  

* Delay apply to water level in mm
  In mm water level during history data from Netatmo Rain module

* Delay apply based on history rain in hours
  How many history hours will be used for calculate rain water level
  
* Check interval
  How often will be checked weather
  
* Use Cleanup Delay
  If Delay will be removed when weather in nice

====

This plugin checked weather forecast.  
When weather-based rain delay is enabled, the weather will be checked for rain every hour.  
If the weather reports any condition suggesting rain, a rain delay is automatically issued using the below set delay duration.

Plugin setup
-----------

* Check Use Automatic Rain Delay:  
  If checked use automatic rain delay plugin is enabled.  
   
* Delay Duration (hours):  
  Type  delay duration in hours (minimum is 0, maximum is 96 hours).

* Weather Provider:  
  Select weather provider (Wunderground, Yahoo).  

* Wunderground API Key:  
  Type Wunderground API Key for Your account.  
  Account for API is [here](http://www.wunderground.com/weather/api/).  
  Example: c1511565611663 

* Status:  
  Status window from the plugin.  

