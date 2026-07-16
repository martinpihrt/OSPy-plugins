Monthly Water Level Readme
====

Tested in Python 3+

Enter an adjustment for each month (% irrigation time).  
The water level will be adjusted accordingly. 

The plug-in includes an OSPy `plugin.json` manifest, registers its daily
adjustment worker with the shared plug-in runtime, uses the common stop signal,
and implements `health()`. Diagnostics reports worker state, current month,
configured percentage, the factor applied to OSPy, latest successful update,
and recent errors. Stopping the plug-in removes its global water-level
adjustment.

Plugin setup
-----------

* Enter an adjustment for January - December:  
  value range is 0-999 (0 = 0% to 999 = 999% water run Time)
