LCD Settings Readme
====

This plugin shows information on 16x2 character LCD with PCF8574.  
Automatically detects the display at the following I2C addresses: 0x20-0x27, 0x38-0x3F.  
Compatible with the HD44780 controller.  

Plugin setup
-----------
* Check Use I2C LCD:  
  If checked use I2C lcd plugin is enabled and print messages on the LCD display.  </br>

* HW version I2C PCF8574<->LCD:  
  Select type Hardware board with PCF8574. Conection with LCD driver:  
  a) Lower 4 bits of expander are commands bits  
  b) Top 4 bits of expander are commands bits AND P0-4 P1-5 P2-6 (Use for LCD1602 board)  
  c) Top 4 bits of expander are commands bits AND P0-6 P1-5 P2-4  
  d) LCD1602 board where lower 4 are commands, but backlight is pin 3  
  e) LCD board (https://pihrt.com/elektronika/315-arduino-uno-deska-i2c-lcd-16x2)  </br>

* Check Use print lines to debug files:  
  If checked use print lines to debug files line 1 or line 2 print to debug files.  
  (warning: If you enable this debug file will have a huge size).  </br>

* Display: If checked print state message to LCD display
System Name:  
SW Version Date:  
IP:  
Port:  
CPU Temp:  
Time and Date:
Uptime:  
Rain Sensor:  
Last Run Program:  
Pressure Sensor:  
Water Tank Level:  
Running Stations:  
DS18B20 Temperature: </br>


* Status:
  Status window from the plugin.  
  Example message on the LCD display:  
  OpenSprinkler Py (text on line 1)
  Irrigation system (text on line 2)    
  CPU temperature:  
  42.8 C  
  Date: 17.02.2015  
  Time: 12:22:57  
  OSPy version:  
  2015-02-17  
  System uptime:  
  5:12:11  
  My IP is:  
  https://192.168.4.184/8080  
  My port is:  
  8080  
  Rain sensor:  
  Inactive  
  Last program:  
  None  
  Pressure sensor:    
  Not available  
  Water Tank Level:
  Level 120 cm 100%, volume 1.25 m3, ping 86 cm
  DS1-6 Temperature:  
  23.5, -127, 23.5, 36.5, 78.0, -127
  (-127 is not connected probe to hardware board...)  </br>

* Important status information OSPy:
  If events occur in the system: restart, poweroff, update available, they will be displayed preferentially regardless of the above settings.  </br>     
  
## The hardware should be connected as follows (LCD board by pihrt.com)
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/schematics.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/schematics.png)

## The LCD 1602 IIC with PCF8574 (Top 4 bits of expander are commands bits AND P0-4 P1-5 P2-6)
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/lcd1602_iic.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/lcd1602_iic.png)  

## PCF8574 address map
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/pcf8574_map.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/lcd_display/static/images/pcf8574_map.png)    

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/315-arduino-uno-deska-i2c-lcd-16x2). for more information.
