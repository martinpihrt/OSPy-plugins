Direct 16 Relay Outputs Readme
====

Tested in Python 3 and Python 2

This is plugin is designed for use with Raspberry Pi models with a 40 pin GPIO header and example this board: https://www.tiaowiki.com/w/TIAO_Smart_Sprinkler_Pi_Hardware_Layout. This plugin allows OSPy to control relay boards with up to 16 relays.<br>
The diagram below shows the GPIO pin header and indicates the pins to use with this plugin.<br>
You can use a relay board with 1, 2, 4, 8 or 16 relays or a combination of those up to 16 relays.<br>
<br>
<b>Caution:</b> when using more than 1 relay board, the boards must all be either low-level trigger or all high-level trigger. You can not mix the trigger types.<br>
<b>Warning:</b> if you use all 16 outputs, you will not use the UPS Monitor and Air Temperature and Humidity Monitor<br>
<br>
Connect the board(s) to the Raspberry Pi following the channel numbering indicated on the wiring diagram. 

The hardware should be connected as follows:
Possible GPIO [22,24,26,32,36,38,40,21,23,29,31,33,35,37,18,19] Station 1 as HW pin 22, Station 2 as HW pin 24 etc...<br>
<a href="/plugins/relay_16/static/images/schematics.png"><img src="/plugins/relay_16/static/images/schematics.png" width="100%"></a>

The 5V and ground pins on the Pi can be used to power 1 or 2 relay boards. If more boards are being used or if more than a couple of relays will be turned on at the same time It is a good idea to use a separate power supply to power the boards.<br>
If you are using more than 8 channels and need to increase the number of stations OSPy displays, open the Options menu > Station Handling and incrase the number of Extension boards. Increasing the number by 1 will add 8 stations to OSPy.<br>
If the number of relays you are using is not a multiple of 8 you can hide the unused stations. Open the Stations menu and uncheck the boxes under Enabled? next to the stations you are not using.  

Plugin setup
-----------
* Check Enable relays:  
  If checked plugin is enabled.  
* Relay channels:  
  Select outputs (1-16).  
* Trigger Level:  
  LOW = Station is ON (Output set to 0V), Station OFF (Output set to 3.3V)  
  HIGH = Station is ON (Output set to 3.3V), Station OFF (Output set to 0V)     
* Status:  
  Status window from the plugin.  
  Example:  
  Relay 16 plug-in: 2018-06-06 10:35:08 3 Outputs set.  
  Relay 16 plug-in: Possible GPIO [22,24,26,32,36,38,40,21,23,29,31,33,35,37,18,19].  
  Relay 16 plug-in: 2018-06-06 10:35:08 Setings Relay Output 22 to HIGH (Station 1 ON).  
  Relay 16 plug-in: 2018-06-06 10:35:28 Setings Relay Output 22 to LOW  (Station 1 OFF).  

Visit [Martin Pihrt's blog](https://pihrt.com). for more information.  
