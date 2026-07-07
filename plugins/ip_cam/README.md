IP Cam Readme
====

Tested in Python 3+

This extension displays JPEG previews, GIF animations and proxied MJPEG streams from IP cameras. Each OSPy station can have one camera address, optional login credentials, a JPEG snapshot path and an optional MJPEG stream path.

Camera address and paths
-----------

Enter only the camera base address in **IP address and port**, for example:

* `http://192.168.1.120`
* `http://192.168.1.120:88`
* `https://camera.example.com`

Enter only relative paths in the JPEG and MJPEG query fields. Username and password belong in the separate access fields.

Common presets
-----------

The setup page has a manufacturer preset selector for each camera. Selecting a preset fills the JPEG and MJPEG query fields for the currently selected station.

* Hikvision:
  * JPEG: `ISAPI/Streaming/channels/101/picture`
  * MJPEG: `ISAPI/Streaming/channels/102/httpPreview`
* Dahua / Amcrest:
  * JPEG: `cgi-bin/snapshot.cgi`
  * MJPEG: `cgi-bin/mjpg/video.cgi?subtype=1`
* AVtech:
  * JPEG: `cgi-bin/guest/Video.cgi?media=JPEG&channel=1`
  * MJPEG: `cgi-bin/guest/Video.cgi?media=MJPEG&channel=1`
* Axis:
  * JPEG: `axis-cgi/jpg/image.cgi`
  * MJPEG: `axis-cgi/mjpg/video.cgi`
* Foscam:
  * JPEG: `cgi-bin/CGIProxy.fcgi?cmd=snapPicture2`
  * MJPEG: `cgi-bin/CGIStream.cgi?cmd=GetMJStream`

Plugin setup
-----------

* Camera enabled:
  Enables or disables one camera without deleting its settings.

* Use JPEG image downloads:
  Downloads JPEG snapshots to the plugin data folder. The latest snapshot is stored as `N.jpg`, where `N` is the station number.

* Use GIF image creating:
  Stores each successful JPEG download as a GIF frame and creates `N.gif` from the newest frames. Failed downloads are not copied as new frames, so a GIF contains only real successful snapshots.

* Allow IP Cam images on home:
  Allows OSPy to use IP Cam images on the home page when the OSPy System option **Station picture source** is set to IP Cam JPG or IP Cam GIF.

* Number of frames in GIF:
  Number of successful snapshots kept for GIF generation.

* Download interval:
  Seconds between automatic JPEG downloads.

* HTTP timeout:
  Timeout for camera HTTP requests.

* Maximum image size:
  Maximum cached JPEG image size from one camera. Oversized downloaded JPEG images are resized before saving when possible. Generated GIF animations are resized to stay under this limit when possible.

* GIF frame delay:
  Duration of one frame in the generated GIF animation.

* Verify SSL certificates:
  Verify HTTPS camera certificates.

Diagnostics and test buttons
-----------

* Snapshot now:
  Downloads the selected camera JPEG immediately and stores it as `N.jpg` in the plugin data folder.

* Test JPEG:
  Tests the JPEG path and updates diagnostics. A successful test also saves the latest snapshot.

* Test MJPEG:
  Opens the MJPEG stream, reads the first available data block and closes the connection. It is only a connectivity test.

The main page shows the last download time, HTTP status and text, response time, image size, resolution, GIF frame count, success/error counters and the last error.

Snapshot management
-----------

The main page has a **Snapshots** button. This page lists cached `N.jpg` snapshots and `N.gif` animations, shows a preview, file size and modification time, and allows downloading or deleting individual files. The page only shows real IP Cam cached files. If a requested cached file does not exist yet, downloads show a clear notice instead of an empty `none` response. The **Delete cached images** action removes all cached snapshots, GIF files and GIF frame folders.

Troubleshooting
-----------

* `401 Unauthorized` usually means wrong credentials or camera authentication mode. Check username/password and try enabling Basic or Digest authentication in the camera.
* `403 Forbidden` usually means the user has no permission for snapshot or stream access.
* `404 Not Found` usually means the selected path is wrong for that camera model.
* Timeout usually means wrong IP/port, blocked network access, HTTPS certificate problems or a camera that is slow to respond.
* If GIF has fewer frames than expected, check whether every JPEG download succeeds. Only successful downloads are used as GIF frames.
* If GIF files become too large for the OSPy home page, lower **Maximum image size** or **Number of frames in GIF**. The GIF generator resizes frames and the final animation to stay below the configured maximum size when possible. Existing oversized GIF files are regenerated from cached frames when they are used and frames are available.
* If IP Cam JPG/GIF is selected as the OSPy home page image source and the plug-in is not installed or no cached image exists, OSPy falls back to the uploaded station image and then to the default no-image picture.

The MJPEG stream is proxied through OSPy so the camera username and password are not embedded in the browser image URL.
