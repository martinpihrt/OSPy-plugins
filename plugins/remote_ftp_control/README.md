Remote FTP Control Readme
====  

This plug-in makes downloading and uploading text file on the remotely via FTP for remotely control OSPy system every 60 seconds. When you first start the plug-in detects whether ramdisk is present, otherwise it creates and writes fstab.
If plug-in says: "restart your linux os system!" You must manual reboot os via options/reboot os. This plugin required Webserver with PHP and FTP.

Plugin setup
-----------
* Check Use plug-in:  
  If checked use plug-in Remote FTP Control plug-in is enabled and control your OSPy.

* The FTP server address:  
  Type the address of your FTP server. Ex: 1234.w0.wedos.net

* The FTP user name:  
  Type the of your user name for FTP server. 
  
* The FTP user password:  
  Type the of your user password for FTP server. 

* The FTP server location for files:  
  Type where is located data.txt and stavy.php on the FTP server. If file is in root folder use "/" else use "/xxx/yyy/zzz".

* Status:  
  Status window from the plug-in.  
  ex:  
  FTP connection established.  
  FTP received data from file data.txt: OK  
  Data file stavy.php has send on to FTP server: 09.08.2016 (21:02:53)  
  
Server setup
-----------  
* On the Web server will place these files (after unpacking the zip file).  
  <a href="https://github.com/martinpihrt/OSPy-PHPfileFTP/archive/master.zip">download PHP for Remote FTP Control.zip files from github</a>
* On the WEB server we places files as in imagge:  
  <a href="/plugins/remote_ftp_control/static/images/web.png"><img src="/plugins/remote_ftp_control/static/images/web.png" width="100%"></a>
* On the WEB server use .htaccess and .htpasswd files for secured login for your OSPy control.  


