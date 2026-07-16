Usage Statistics Readme
====
Tested in Python 3+

This plugin prints all available statistics from all users OSPy systems. 
In the OSPy system is embedded statistical sending anonymous data (specifically python version, general information about the operating system - architecture, distribution, system, OSPy system version).
Read from source [pihrt.com](https://pihrt.com/ospystats/statistics.json). File on the server is updated every hour.
  *  The data from www.pihrt.com was downloaded correctly. xxxx-xx-xx xx:xx:xx
Last downloaded data from server. Or Error: data cannot be downloaded from www.pihrt.com! if file is corrupted or not downloaded.
  *  Your ID is: xxxxxx-xxxxxx-xxxxxx  
Your specific anonymous ID in table on the server.

The plug-in includes an OSPy `plugin.json` manifest, registers its refresh
worker with the shared plug-in runtime, uses the common stop signal, and
implements `health()`. Diagnostics reports worker state, source URL, record
count, and the last successful refresh.


