Voice Station Readme
====

Tested in Python 3+

This plugin allows you to use voice notifications for stations events in the OSPy system. Into the Connector from Output on Raspberry Pi connect Amplifier and Speakers for voice notification. If more than one station is activated in a row, the songs are added to the queue and then played from the queue. You can upload any song with any name in mp3 and wav format to the song directory. Unlike the "voice notification" package, this extension has no connection to the station scheduler (ie how the programs and the stations assigned in them are set up). In this extension, the song will be played whenever the station status changes, regardless of what event the status triggered (for example, manual mode, scheduler, or some other plugin...)

Plugin setup
-----------

* Enable voice:  
  If the check box is marked, the extension will be active.
  
* Master volume:  
  Setting the Raspberry Pi output volume (0 - 100%).
  
* Play only from:  
  Play notifications only from this time (0 - 23 hour).
  
* Play only to:  
  Play notifications only to this time (0 - 23 hour).
 
* Status:  
  Status window from the plugin.

* Upload sound file:  
  file must be in mp3 or wav format!

Visit [Martin Pihrt's blog](https://pihrt.com). for more information.  
