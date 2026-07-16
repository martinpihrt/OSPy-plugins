Weather-based Water Level Readme
====

Tested in Python 3+

When weather-based water level is enabled, the weather will be checked every hour and the water level will be adjusted accordingly.
In addition, it is now able to protect plants against freezing during selected months.
If weather data is temporarily unavailable, the plugin logs the problem and leaves the current water level adjustment unchanged.

The plug-in includes a manifest declaring weather-network, irrigation-adjustment and freeze-protection access, uses the shared OSPy worker lifecycle, removes its callback, footer and adjustment during shutdown, and reports its latest calculation through the Diagnostics health interface.

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
  Type forecast days (minimum is 0, maximum is 7).

* Show in footer:
  Show a short status on the OSPy home page footer with the last calculation time, missing rainfall and the current water adjustment.

* Forecast details:
  Opens a detail page with the last weather calculation. The page shows the used history, today and forecast days, including hourly data count, rainfall, average temperature, wind, humidity and the resulting water level adjustment.

* Protect against freezing:  
  If checked Protect against freezing plugin monitors temperature and protects stations from freezing.
  
* Protect temperature:  
  Type temperature to activate protection.

* Protect minutes:  
  Type time in minutes for protection.

* Protect stations:  
  Select all stations for protection.

* Protect months:  
  Select all months for protection.

* Status:  
  Status window from the plugin.  

Note:
If you set the minimum percentage to 0%, the station time can be set to 0%. As a result, in the preview program on the main page it can look like the program is not working.
