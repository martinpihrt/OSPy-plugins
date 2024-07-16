Shelly Cloud Integration Readme
====

Tested in Python 3+

How to get the latest device status via Shelly Cloud API and curl. Path: https://server_uri/device/status.
Supported methods: GET and POST.
Parameters are supplied via query or request body
Required data to send the request:
Target device ID: key = "id"
account authentication key: key = "auth_key"
The result is a JSON object with the device status.
The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key.

Plugin setup
-----------

* Server uri:  
  The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key.

* Auth key: 
  This can be obtained from Shelly > User Settings > Cloud Authorization Key.

* Request intervalg: 
  Shelly cloud data download recovery interval.

* Use sensor: 
  If you do not want to use the sensor but do not want to delete it in the list, uncheck the box.

* Label for Shelly sensor:  
  Your Shelly designation (Shelly will be available in the OSPy system under this designation).

* Shelly sensor ID:  
  Unique ID number to identify Shelly devices. It can be found in the Shelly device settings or on the Shelly manufacturer's cloud site: https://control.shelly.cloud after logging in, click on the desired device and the "device information" section.

* Shelly sensor type:
  Shelly Plus HT, Shelly Plus Plug S, Shelly Pro 2PM

* Status:  
  Status window from the plugin.


