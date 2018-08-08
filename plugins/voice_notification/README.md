Voice notification Readme
====

This plugin allows you to use voice notifications for different events in the OSPy system. Into the Connector from Output on Raspberry Pi connect Amplifier and Speakers for voice notification. This plugin requires pygame installed. If pygame is not installed on the system, plugin it will install it himself. Pygame is comes already installed on the default Raspberian installation.
The plugin will always play voice.mp3 and next then the sound assigned to the station (for example: voice3.mp3).

Plugin setup
-----------

* Enable voice:  
  If the check box is marked, the extension will be active.

* Enable pre start voice:  
  If the check box is marked, the sound is played before turning on the station.

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

* Upload mp3 file:  
  MP3 file must have a name "voice.mp3","voice0.mp3","voice1.mp3",...!

Visit [Martin Pihrt's blog](https://pihrt.com). for more information.  
