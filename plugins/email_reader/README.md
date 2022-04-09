E-mail Reader Readme
====

Tested in Python 3 and Python 2

This extension allows you to retrieve data from a configured E-mail box and respond to incoming messages that arrive in the mailbox. This extension requires the email_notification extension to be installed and set up correctly. We will send receive messages using the set account. After receiving and processing the message in the E-mail, a confirmation of the message processing will be sent.  

Plugin setup
-----------

* Use E-mail reader:  
  Activate this extension for reading E-mails and control OSPy.  

* E-mail recipient name:  
  E-mail account login details (typically something@something.com).  

* E-mail  recipient password:  
  E-mail account login password.  

* IMAP Server:  
  E-mail IMAP provider (typically imap.gmail.com).  

* Use SSL:  
  Enable SSL connection.  

* Move to trash:  
  Move the message to the Trash after reading.  

* Recipient folder:  
  E-mail recipient folder (typically INBOX).  

* Sender for control access:  
  E-mail user address from whom incoming messages will be processed.  

* Checking interval:  
  After how long to check incoming mail in the inbox. The check time is set in seconds. Minimum is 30.  

* E-mail incoming subject:  
  The subject of the incoming message. In this way, we can ensure minimum security (such as a password), or differentiate the different OSPy systems.    

* Send reply:  
  After processing the received message, send an email with the subject below. The email_notification extension is required for this function.  

* E-mail subject:  
  The subject of the message being sent.  

* Status:  
  Status window from the plugin.  


Example for control
-----------

* Sending message in body E-mail as list (use in manual mode):  
  Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...  
```bash
[0,0,100,30]    
``` 

* Sending message in body E-mail as dict (use in manual mode):  
  Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...  
```bash
{"station name 1": 0, "station name 2": 0, "station name 3": 100, "station name 4": 30}  
```  

* Sending message in body E-mail for switch scheduler to ON:  
```bash
scheduler_on  
```  

* Sending message in body E-mail for switch scheduler to OFF:  
```bash
scheduler_off  
```  

* Sending message in body E-mail for switch to manual mode:  
```bash
manual_on  
```  

* Sending message in body E-mail for switch to scheduler mode:  
```bash
manual_off  
```  

* Sending message in body E-mail for stop all running stations:  
```bash
stop_run  
```  

* Sending back all setuped commands via E-mail:  
```bash
send_help  
```  

* Sending back all stations state via E-mail:  
```bash
send_state  
```  

* Sending back temperature states via E-mail:  
```bash
send_temperatures  
```  

* Sending back tank states via E-mail:  
```bash
send_tank  
```  

* Sending back wind states via E-mail:  
```bash
send_wind  
```  

* Selecting command xx:  
  Sending command in  message body E-mail for run  via selecting.  
  Reboot OS system, Shutdown OS system, Run program 1-8 if exists.