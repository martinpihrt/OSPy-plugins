Weather-based Water Level Netatmo Readme
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

Added Daily water level - in default plug-in was defined 4 - You can customize water level need by you.
In status line is added history data of rain from both websites and forecast.  

====

When weather-based water level is enabled, the weather will be checked every hour and the water level will be adjusted accordingly.

Plugin setup
-----------
* Check Use Automatic Water Level Adjustment:  
  If checked use automatic water level adjustment plugin is enabled.  
  
* Min percentage:  
  Type min percentage (minimum is 0, maximum is 100).    

* Max percentage:  
  Type max percentage (minimum is 0, maximum is 1000).

* History days used:  
  Type history days (minimum is 0, maximum is 20).

* Forecast days used:  
  Type forecast days (minimum is 0, maximum is 10).

* Status:  
  Status window from the plugin.  

note:  
if you set the minimum percent to 0%, the time switch stations set to 0. In the preview program on the main page, then it looks like the program is not working.
