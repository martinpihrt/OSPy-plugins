Telegram Bot Readme
====

Tested in Python 3 and Python 2

In the telegram application, we send a message to user @botfather and confirm it */start*.  
Create a new bot with the */newbot* command and specify what the bot will be named ex: ospyk_bot (name must end with *_bot*).  
Use the * /token* command to request the new token (for example: we get something like this 1655412493:AAEPKTaO6KWDS-SCkDLRt2sdfewT4nc0Q).  
Test on webpage https://telegram.me/ospyk_bot. On telegram plugin we insert: token to Subscribee.  
Subscribe to the Announcement list, need an Access Key. Next type your commands (enable, disble, runnow...) for cummunications with bot.  
You must provide a token to enable the bot to talk to telegram, follow the instructions https://core.telegram.org/bots#botfather.  
After starting the extension, it is checked whether a telegram is available in the system.  
If not, the extension will try to install it itself *sudo pip install python-telegram-bot==2.4* for Python 2.7.
*sudo pip3 install python-telegram-bot --upgrade* for Python 3 
After the first start and setup of the extension, we recommend restarting the OSPy.


Plugin setup
-----------

* Enable Telegram Bot:  
  If the box is checked, Telegram Bot A will be enabled.  

* Bot Token:  
  Type your token for enabling the bot to talk with telegram.  Example: 5498756874:AAEPKTa987456SQ.   

* Signals to connect - Zone Change:  
  Send message if there has been a stations changed state.   

* Help Command:  
  Type Help Command for your info. Bot send you available commands for OSPy Control.    

* Info Command:  
  Type Info Command for OSPy info. Bot send OSPy actual states.  

* Start Command:  
  Type Start Command for enabling OSPy scheduler.  

* Stop Command:  
  Type Stop Command for disabling OSPy scheduler.  

* RunOnce Command:  
  Run Once Command, use program number as argument. 

* Stop Command:  
  Stop Command, for stop all running stations and disabling OSPy scheduler.    

* Show in footer:  
  Show data from plugin in footer on home page.   

* Status:  
  Status window from the plugin.  

## Example
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone1.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone1.png) 
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone2.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone2.png) 