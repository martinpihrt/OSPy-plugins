Email Notifications Readme
====

Tested in Python 3+

This plugin can send E-mails. For this plugin you need an E-mail SMTP account as provider (google.com, seznam.cz)...

Plugin setup
-----------
* Check Send E-mail after power on for send E-mail.    
  If checked sends E-mail into your E-mail address.

* Check with log file.  
  If checked with events.log file if exists (your must enabled in options "check Enable debug log").

* Check Send E-mail if rain is detected.
  If checked send e-mail into your E-mail address.  

* Check Send E-mail if a program has finished.
  If checked send E-mail if a program has finished into your E-mail address.  

* SMTP server address:
  Example: smtp.gmail.com

* SMTP port:
  Example: 587 (25)

* Use SMTP username as sender:
  Some SMTP providers prohibit to use another sender than the same mail user.

* SMTP username:  
  Type your E-mail password.

* SMTP password:  
  Type your E-mail password.

* Send E-mail to:  
  Type more E-mail address for recipient E-mail post office.
  
* E-mail subject:
  Type E-mail subject for send E-mail.  

* Save and send it later:
  If there is no Internet connection, save and send it later.

* Status:
  Status window from the plugin.  

This extension also sends some statuses from other extensions (if they are installed on the system). For example temperature, flow...

Example recieve E-mail
-----------

Systém 2021-07-10 18:11:33
Ukončené zalévání
Program: Jednorázový
Stanice: Ventilátor sklep
Čas startu: 2021-07-10 18:11:29
Trvání: 00:04 
Voda
Množství vody v zásobníku: Úroveň: 192 cm (72 %), Ping: 211 cm, Objem: 1448.25 litrů 
Čítač spotřeby vody
Měřeno od dne: 2021-04-01 10:18:10, Hlavní stanice: 56.97 m3, Druhá hlavní stanice: 0.0 Litr 
Teplota DS1-DS6
SKLEP: 20.0 C
BAZÉN: 21.0 C
BOJLER: 59.3 C
UVNITŘ: 21.6 C
STUDNA: 15.0 C
VENKU: 31.0 C
Snímače
S1: 21.3 C
S2: Kontakt spojený
S3: 68 cm (100 %)
