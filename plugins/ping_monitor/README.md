Ping Monitor Readme
====

This extension allows you to ping addresses. All pings are recorded in a file (always the first successful and the first unsuccessful).
The log file (pings) can be sent by E-mail after a certain time. At the same time, we can restart the device after a certain number of unsuccessful attempts. 

* Download log as csv
  Allows you to download a csv file to your computer.

If logging is enabled, a graph with measured data will be displayed at the bottom of the screen.  

Plugin setup
-----------
* Use ping monitoring:    
  Activate this extension use for ping testing.  

* Ping address 1, 2, 3:  
  1-3 address for testing. 

* Ping interval:  
  After what time do we want to repeat the ping. From 2 to 600 seconds.

* Number of invalid pings to restart the device:  
  If enabled restart this device, then this item affects how many unsuccessful pings will be performed before a restart. From 2 to 60.  

* Restart this device:  
  When enabled, the device will be restarted after a certain number of unsuccessful pings (HW restart).

* Send an E-mail with statistics (csv file):  
  Send a csv file with statistics via E-mail.

* Interval for sending statistics:  
  Interval for sending statistics by email. From 1 to 48 hours.

* Delete statistics after send:  
  Delete the csv file with statistics after sending the E-mail and create a new clean file.

* E-mail subject:  
  The subject of the message being sent.

* Enable logging:  
  When logging is enabled, a log file is created (required for the graph and for sending an e-mail at the same time).  

* Select filter for graph history  
  Without limits  
  Day filter  
  Month filter  
  Year filter      

* Status:  
  Status window from the plugin.  
