# OSPy-plugins Changelog

July 06 2026
-----------
martinpihrt - IP Cam<br/>
Changed IP Cam snapshot previews to embed cached JPG/GIF files directly in the Snapshots page instead of issuing separate preview requests, avoiding 404 preview errors, and changed the main IP Cam status image size display from bytes to KB.

martinpihrt - IP Cam<br/>
Fixed IP Cam snapshot management so missing cached files no longer preview normal station fallback images, and oversized downloaded JPEG snapshots are resized before saving when possible so `N.jpg` cache files can still be created for the Snapshots page and OSPy home images.

martinpihrt - LCD Display<br/>
Added a Wind Speed display switch that shows current and maximum wind speed from Wind Speed Monitor, and re-initializes the HD44780/PCF8574 LCD at the start of each display cycle without re-scanning the I2C address to recover from corrupted characters during long operation.

martinpihrt - IP Cam<br/>
Fixed IP Cam snapshot responses so missing cached JPG/GIF files no longer render as blank previews or a `none` download response, added colored camera setup headers for configured/missing cameras, added a local Submit button beside camera test actions, and changed GIF creation to normalize frames, resize the final animation according to Maximum image size when possible, and regenerate existing oversized GIF files from cached frames when available.

martinpihrt - IP Cam<br/>
Fixed IP Cam setup safety and snapshot handling: setup rendering no longer resets all configured cameras after a template error, camera tests in setup now submit and save the current form before testing and stay on the setup page, and snapshot previews use a separate preview response while downloads keep attachment headers.

martinpihrt - IP Cam<br/>
Added an IP Cam Snapshots management page for cached JPG/GIF previews with download and delete actions, changed setup camera sections to collapsible panels, kept setup tests on the setup page with success/failure messages, widened the status area, removed redundant station numbers from camera card titles, fixed GIF preview sizing, and documented the OSPy home-image fallback behavior.

martinpihrt - IP Cam<br/>
Improved IP Cam usability: camera settings now have a top save action, per-camera enable switches, one-camera-at-a-time selection, manufacturer presets for common JPEG/MJPEG paths, test buttons directly in setup, framed equal-size camera cards with status first, richer HTTP diagnostics with status explanations, home-page image support through OSPy source selection, more detailed help/README troubleshooting, and more reliable GIF generation from real successful snapshots.

martinpihrt - IP Cam<br/>
Improved IP Cam with per-camera diagnostics, manual Snapshot/Test JPEG/Test MJPEG actions, safe MJPEG proxy streaming without exposing camera credentials in browser URLs, configurable download interval, HTTP timeout, SSL verification, maximum image size, GIF frame delay, cache cleanup, and updated setup/help documentation.

martinpihrt - Label Maker<br/>
Updated Label Maker help and README dependency text after the built-in EAN13 barcode generator change. The documentation now separates QR, QR with logo and EAN13 requirements and notes that python-barcode is no longer needed.

martinpihrt - Label Maker<br/>
Added advanced QR settings for module size, border, error correction, foreground/background color, a configurable PNG download filename, clearer preview/download controls, and client/server-side input validation.
Stopped automatic pip installs for missing Label Maker dependencies on externally managed Python environments. The plug-in now logs apt package hints and no longer reports the normal POST redirect as an error.
Added an Install libraries button to the Label Maker settings page when required system packages are missing, with installation progress shown in the status log.
Replaced the EAN13 python-barcode dependency with an internal EAN13 PNG generator using Pillow, avoiding the unavailable python3-barcode package on Raspberry Pi OS Bookworm.

martinpihrt - IP Scanner<br/>
Changed the common web ports option from a checkbox to a switch-style control.

martinpihrt - IP Scanner<br/>
Improved IP Scanner with active local network discovery, network summary, structured device table, hostname and vendor hints, Gateway/This OSPy/Sensor candidate notes, and optional checks for common web ports 80, 443, 8080 and 8081.

martinpihrt - Weather-based Water Level<br/>
Added a Forecast details page that shows the last weather calculation input and result, including history, today and forecast rows with rainfall, average temperature, wind, humidity and the resulting water level adjustment.

martinpihrt - Signaling Examples<br/>
Updated the Signaling Examples plug-in to use a single complete signal list shared by code, settings, help, and README documentation. The settings page now refreshes status automatically and shows the last received signal in a separate auto-updating field.

martinpihrt - LCD Display, Wind Speed Monitor<br/>
Improved I2C bus cooperation between LCD Display and Wind Speed Monitor: Wind Speed Monitor now requests high-priority I2C access for PCF8583 counter setup and reads, while LCD Display uses low-priority short-timeout access so display scrolling does not delay time-sensitive measurements.
LCD Display now uses HD44780 display-shift commands for scrollable text that fits into the controller DDRAM buffer, reducing I2C traffic while preserving full long-text scrolling behavior for longer messages.
