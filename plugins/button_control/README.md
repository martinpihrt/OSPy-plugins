Button Control Readme
====

This plugin uses a circuit board with MCP23017 controller connected to the OSPy Sprinkler board via the I2C interface.  
This plug-in includes eight buttons with optional functions and signalisating via eicht LEDs.  
Visit <a href="https://pihrt.com/elektronika/323-moje-raspberry-pi-plugin-ospy-8-tlacitek-8-led">Martin Pihrt's blog</a> for more information.    
I2C address for MCP23017: 0x20 to 0x27.  

Plugin setup
-----------
* Check Use Button:  
  If checked use button plugin is enabled.  

* Address for MCP23017 controller:
  Selector for I2C address in range 0x20 to 0x27.  

* First stop:  
  First stop everything running and then start the program.   
  If we want to start a new program and add it to the running ones, we will leave this option off.  

* Select:  
  Run-now program 1  
  Run-now program 2  
  Run-now program 3  
  Run-now program 4  
  Run-now program 5  
  Run-now program 6  
  Run-now program 7  
  Run-now program 8  
  Restart system (OS system)  
  Shutdown system (OS system)  
  Stop stations  
  Enable scheduler  
  Disable Scheduler  
* Status:  
  Status window from the plugin.   
