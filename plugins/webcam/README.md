Webcam Monitor Readme
====

Tested in Python 3+

This plugin show image from USB Webcam. This plugin needs fswebcam.  
If fswebcam is not installed, install it from the system package manager.

The plug-in includes an OSPy `plugin.json` manifest and implements `health()`.
Diagnostics reports whether capture is enabled, `/dev/video0` and `fswebcam`
are available, and a snapshot has been created.


Plugin setup
-----------
* Download image as:  
  Open new window in full resolution for downloading image.

* Check Enabled:  
  If checked enabled plugin is enabled.

* Resolution:
  Type resolution for Your USB webcam X-Y (default is 1280x720).
  
* Flip image horizontally:  
  If checked flip image horizontally image from cam is flip horizontally.

* Flip image vertically:    
  If checked flip image vertically image from cam is flip horizontally.

* Status:
  Status window from the plugin.  

