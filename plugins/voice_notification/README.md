Voice notification Readme
====

Tested in Python 3 and Python 2

This plugin allows you to use voice notifications for different events in the OSPy system. Into the Connector from Output on Raspberry Pi connect Amplifier and Speakers for voice notification. This plugin requires pygame installed. If pygame is not installed on the system, plugin it will install it himself. Pygame is comes already installed on the default Raspberian installation. The plugin will always play sound and next then the sound assigned to the station (for example: voice3.mp3). Unlike the "voice station" package, this extension has a connection to the program scheduler (ie how the programs and stations assigned in them are set up.) In this extension, the song is played some time before the program starts.

Plugin setup
-----------

* Enable voice:  
  If the check box is marked, the extension will be active.

* Pre run time:  
  How many seconds before turning on stations play sound (1 - 59 sec).
  
* Repeat playback:    
  How many times to repeat the same message (1 - 3x).
  
* Master volume:  
  Setting the Raspberry Pi output volume (0 - 100%).
  
* Play only from:  
  Play notifications only from this time (0 - 23 hour).
  
* Play only to:  
  Play notifications only to this time (0 - 23 hour).
  
* Skip stations:  
  Skip voice notification for these stations (multiple select).
  
* Select voice for stations:  
  Select voice for this station (voice0.mp3-voice20.mp3)
 
* Status:  
  Status window from the plugin.

* Upload sound file:  
  file must be in mp3 or wav format!

Visit [Martin Pihrt's blog](https://pihrt.com). for more information.  
