��            )   �      �     �     �     �     �     �  '   �  ~        �     �  i   �  K     E   _     �     �     �     �     �  L   �     ,     =     R  *   ^  B   �  (   �     �                    +  �  /     �     �     �     �       A     �   O  )   4	     ^	  �   j	  b   =
  �   �
     .      K  	   l     v     {  p   �     �          ,  S   >  }   �  <     "   M     p     |     �     �                                                                                         
                                            	    Cancel E-mail subject Email was not sent Email was sent FAULT For this function required email plugin If is error with power line in a certain time, sends plugin email with error and shutdown system (and generate pulse to GPIO). Max time for shutdown countdown OK Output on GPIO 24 - pin 18 (via optocoupler open colector and ground) to UPS for shutdown battery in UPS. Power line is connected via optocoupler between GPIO 23 - pin 16 and ground Power line is not restore in time -> sends email and shutdown system. Power line state Send email with error Sent Status Submit This plugin checked power line for system. UPS (uninterrupted power supply). Time to shutdown UPS monitor settings UPS plug-in UPS plugin - power line has restored - OK. UPS plugin - power line is not restore in time -> shutdown system! UPS plugin detected fault on power line. UPS plugin is started. Unsent Use UPS max 999 minutes sec Project-Id-Version: 
POT-Creation-Date: 2016-06-15 10:36+0200
PO-Revision-Date: 2018-07-22 15:32+0200
Language-Team: 
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 8bit
Generated-By: pygettext.py 1.5
X-Generator: Poedit 2.0.9
Last-Translator: Martin Pihrt <martinpihrt@gmail.com>
Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;
Language: cs_CZ
 Zpět Předmět e-mailu E-mail nebyl odeslán E-mail byl odeslán Chyba Pro tuto funkci je vyžadováno rozšíření Email notifications Pokud vypadne napájecí napětí sítě UPS zdroje a nebude obnoveno do stanovené doby, zašle toto rozšíření E-mail s chybou a následně vypne operační systém (zároveň se vygeneruje krátký puls na GPIO konektoru). Maximální doba pro obnovení napájení V pořádku Výstup z konektoru GPIO-24 pin 18 je přes optočlen (otevřený kolektor) možné použít pro vypnutí a odstavení záložního zdroje UPS - tedy baterií zdroje UPS (pokud tuto funkci Vaše UPS podporuje). Napájecí napětí 230V je přivedeno na optočlen, který spíná konektor GPIO-23 pin 16 na zem Napájecí napětí sítě nebylo obnoveno do stanovené doby -> zasílám E-mail s chybovou zprávou a vypínám operační systém (Linux). Stav napájení (síť 230V) Zaslat E-mail v případě chyby Odeslané Stav Potvrdit Toto rozšíření kontroluje napětí sítě (napájení záložního zdroje UPS - Uninterrupted Power Supply). Čas do vypnutí systému Rozšíření UPS nastavení Rozšíření UPS Rozšíření UPS - napájecí napětí ze sítě bylo obnoveno (vše v pořádku). Rozšíření UPS - napájecí napětí ze sítě nebylo obnoveno do stanovené doby -> vypínám operační systém (Linux)! Rozšíření UPS zjistilo problém s napájením ze sítě. Rozšíření UPS bylo spuštěno. Neodeslané Použít UPS rozšíření maximum 999 minut vteřin(a/y) 