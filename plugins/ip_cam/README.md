IP Cam Readme
====

Tested in Python 3+

This extension allows you to display image preview and image stream from IP cameras. Each station in OSPy is assigned a camera address, optional login credentials, a JPEG image path and an optional MJPEG stream path.

Example for a Hikvision IP camera:

* IP address and port: `http://ipaddress:port`
* JPEG query: `ISAPI/Streaming/channels/101/picture`
* MJPEG query: `ISAPI/Streaming/channels/102/httpPreview`
* Username and password: set in the separate access fields.

Plugin setup
-----------

* Use JPEG image downloads:
  When this option is checked, JPEG images will be downloaded after 5 seconds to the plugin folder and these images will be previewed on the web page. This option will make it possible to see preview images even from an external IP address. 

* Use GIF image creating:
  When this option is checked, JPEG images will be downloaded after 5 seconds (after 5 seconds an image is created - a gif animation is then created from xx images) to the plugin folder and these images will be previewed on the web page as GIF animation. This option will make it possible to see preview images even from an external IP address.

* Number of frames in GIF:
  How many images from the camera are saved and then used to create a GIF image. (The more frames, the longer the gif will be refreshed. Frames are created every 5 seconds. eg: 10 frames - gif is created in 10x5sec=50sec).  

* Download interval:
  Seconds between automatic JPEG downloads.

* HTTP timeout:
  Timeout for camera HTTP requests.

* Maximum image size:
  Maximum JPEG image size downloaded from one camera.

* GIF frame delay:
  Duration of one frame in the generated GIF animation.

* Verify SSL certificates:
  Verify HTTPS camera certificates.

* IP address and port:
  Example: http://12.34.56.78:88

* Query for get JPEG image:
  Example: cgi-bin/guest/Video.cgi?media=JPEG&channel=1. Use a relative path, not a full URL.

* Query for get MJPEG image:
  Example ISAPI/Streaming/channels/102/httpPreview. Use a relative path, not a full URL.

* Username for access:
  Example: admin

* Password for access:
  Example: 1234

* Status:
  Status window from the plugin. The main page also shows the last download time, HTTP status, response time, image size, resolution, success/error counters and the last error for each configured camera.

The main page contains manual buttons for Snapshot now, Test JPEG, Test MJPEG and Delete cached images. The MJPEG stream is proxied through OSPy so the camera username and password are not embedded in the browser image URL.
