Venetian Blind Readme
====

Tested in Python 3+

This plugin can be used to control blinds and shutters via API and HW module (eg: shelly relays: https://shelly.cloud/products/shelly-25-smart-home-automation-relay/). 
The roller shutter motor is connected to a shelly relay, or some other similar. The relay has two outputs (one for the up direction and the other for the down direction). The relay allows control via the http API rest. The relay also allows you to measure consumption.

Plugin setup
-----------

* Check Use Control:  
  If checked enabled plugin is enabled.  

* Check Enable logging:  
  If checked enabled logging is enabled. 

* Show in footer:  
  Show data from plugin in footer on home page.   

* Number of blinds:  
  Blinds number (eg: 1,2,3...)  

* Label for blind  
  Naming blinds for better identification.

* Command for open blind:  
  Command for open blind (eg: http://192.168.88.213/roller/0?go=open).

* Command for stop blind:  
  Command for stop blind (eg: http://192.168.88.213/roller/0?go=stop).

* Command for close blind:  
  Command for close blind (eg: http://192.168.88.213/roller/0?go=close).

* Command for read status:
  Command for read blind status (eg: http://192.168.88.213/status)

* Label for position 0%:
  Msg if position is 0% (for identification)

* Label for position 100%:
  Msg if position is 100% (for identification)

