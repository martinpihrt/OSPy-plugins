Telegram Bot Readme
====

!!!Not ready for use!!!

In the telegram application, we send a message to user @botfather and confirm it */start*.  
Create a new bot with the */newbot* command and specify what the bot will be named ex: ospyk_bot (name must end with *_bot*).  
Use the * /token* command to request the new token (for example: we get something like this 1655412493:AAEPKTaO6KWDS-SCkDniRLRt2sdfewT4nc0Q).  
Test on webpage https://telegram.me/ospyk_bot. On telegram plugin we insert: token and Bot Access Key - to Subscribee.  
Subscribe to the Announcement list, need an Access Key. Next type your commands (enable, disble, runnow...) for cummunications with bot.  
You must provide a token to enable the bot to talk to telegram, follow the instructions https://core.telegram.org/bots#botfather.  
After starting the extension, it is checked whether a telegram is available in the system.  
If not, the extension will try to install it itself *sudo pip install python-telegram-bot==2.4* For Python 2.7.  
After the first start and setup of the extension, we recommend restarting the OSPy.


Plugin setup
-----------

* Enable Telegram Bot:  
  If the box is checked, Telegram Bot A will be enabled.  

* Bot Token:  
  Type your token for enabling the bot to talk with telegram.

* Bot Access Key - to Subscribe:
  Type your Bot Access key to Subscribe.  

* Signals to connect - Zone Change:  
  Send message if there has been a stations changed state.

* Signals to connect - Stations Scheduled:
  Send message if there has been a stations changed state from scheduler.  

* Info Command:  
  Type Info Command for your info. Bot send you available commands for Control.  

* Start Command:  
  Type Start Command for enabling OSPy scheduler.  

* Stop Command:  
  Type Stop Command for disabling OSPy scheduler.  

* RunOnce Command:  
  Run Once Command, use program number as argument.  

* Status:  
  Status window from the plugin.

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
