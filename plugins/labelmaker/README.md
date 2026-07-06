Label Maker Readme
====

Tested in Python 3+

This extension allows you to generate barcodes or QR codes for your use and subsequent use in the OSPy system (for example, generating flowerbed stickers with a detailed description of what is planted for the variety, the need for soil, water...)

Dependencies
-----------

On Raspberry Pi OS Bookworm and newer, install dependencies with the system
package manager instead of pip:

* EAN13: `sudo apt install python3-pil`
* QR codes: `sudo apt install python3-qrcode`
* QR with logo: `sudo apt install python3-pil`

If a required dependency is missing, the plug-in settings page shows an
Install libraries button. The installation output is written to the plug-in
status log.

Plugin setup
-----------

* Select output format:
  We select the desired code format. We have a selection available:
  BAR EAN13, QR black and white, QR color, QR with logo.

* Message:
  Message embedded in the code. 

* Download filename:
  File name used when downloading the generated PNG image.

* QR module size:
  Size of one QR module in pixels.

* QR border:
  Quiet zone around the QR code.

* QR error correction:
  QR error correction level. Use higher levels when the QR code contains a logo or may be damaged.

* QR color and QR background color:
  Foreground and background colors for color QR codes and QR codes with logo.
 
* Status:  
  Status window from the plugin.
