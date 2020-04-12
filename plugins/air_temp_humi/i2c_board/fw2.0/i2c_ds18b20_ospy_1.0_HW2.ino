/* HW 2.0
 *  zmena oproti HW1.0:
 *  cidla jsou vedena samostatne na svuj vstup
 *  kazde cidlo muze byt az 50 metru daleko od desky
 *  
 * SW 1.0 
 * HW pro OSPy plug-in: temperature and humidity monitor
 * 28.3.2018
 * Martin Pihrt
 * 6 cidel DS18B20, kazde cidlo pripojeno az 50 kabelem k desce
 * 
 * vypis z UARTU (priklad)
OSPy plugin airtemp humi
HW:2.0, FW:1.0, 5.4.2018
Restart CPU za: 59 sec.
Nacitam teplotu...OK
Rozlozena teplota 1: -127.0
Rozlozena teplota 2: -127.0
Rozlozena teplota 3: -127.0
Rozlozena teplota 4: -127.0
Rozlozena teplota 5: -127.0
Rozlozena teplota 6: 026.1
I2C buffer (0-29),11270,11270,11270,11270,11270,00261 
Tik I2C v: 1144 ms.
Restart CPU za: 59 sec.
 */
 
#define FW "HW:2.0, FW:1.0, 5.4.2018"

#define DS1PIN       16      // pin pro 1 cidlo DS18B20
#define DS2PIN       15      // pin pro 2 cidlo DS18B20
#define DS3PIN       14      // pin pro 3 cidlo DS18B20
#define DS4PIN       12      // pin pro 4 cidlo DS18B20
#define DS5PIN       11      // pin pro 5 cidlo DS18B20
#define DS6PIN       10      // pin pro 6 cidlo DS18B20

#define I2C_ADDR    0x03    // I2C adresa tohoto HW
#define WDOG                // pokud neni zakomentovane pouzivame watchdog
#define LED_PIN     17      // kontrolni LED behu CPU
#define LED_SPEED   1000    // rychlost blikani LED a vypis z cidel (1s)


#include <Wire.h> // i2c

#include <OneWire.h>
#include <DallasTemperature.h>  // DS18B20

OneWire DS1oneWire(DS1PIN);
OneWire DS2oneWire(DS2PIN);
OneWire DS3oneWire(DS3PIN);
OneWire DS4oneWire(DS4PIN);
OneWire DS5oneWire(DS5PIN);
OneWire DS6oneWire(DS6PIN);
DallasTemperature DS1cidlo(&DS1oneWire);
DallasTemperature DS2cidlo(&DS2oneWire);
DallasTemperature DS3cidlo(&DS3oneWire);
DallasTemperature DS4cidlo(&DS4oneWire);
DallasTemperature DS5cidlo(&DS5oneWire);
DallasTemperature DS6cidlo(&DS6oneWire);

#ifdef WDOG
   #include <avr/wdt.h>
#endif

unsigned long previousMillis; 
unsigned long last_call;
unsigned int timeout_cal = 60000;    // za 60 sec bude hw restart pokud neni pozadavek od raspi
boolean pripraveno = false; // data jsou pripravena pro I2C k odeslani a muzou se odeslat
boolean pom=false;          // pomocna pro serial

float teplota[6]; // 6 cidel
byte buffer[6*5]; // 6 cidel * 5 byte -> 30 byte buffer


void setup(void) {
  Serial.begin(115200);
  Serial.println(F("OSPy plugin airtemp humi"));
  Serial.println(FW);
  
  #ifdef WDOG
     wdt_enable(WDTO_8S);
     wdt_reset();
  #endif
  
  pinMode(LED_PIN, OUTPUT);
  
  Wire.begin(I2C_ADDR);
  Wire.onRequest(requestEvent); // registr i2c preruseni 
  
  DS1cidlo.begin(); // start sbernice pro DS cidlo 1
  DS2cidlo.begin(); // start sbernice pro DS cidlo 2
  DS3cidlo.begin(); // start sbernice pro DS cidlo 3
  DS4cidlo.begin(); // start sbernice pro DS cidlo 4
  DS5cidlo.begin(); // start sbernice pro DS cidlo 5
  DS6cidlo.begin(); // start sbernice pro DS cidlo 6
  
}//end setup

void loop(void) {
  wdt_reset();
  
  // mereni DS, blikani LED
  if (millis() - previousMillis >= LED_SPEED) {
    previousMillis = millis();
    
    digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // blikame LED
   
    Serial.print(F("Restart CPU za: "));
    unsigned long r;
    r = (last_call/1000)+(timeout_cal/1000)-(millis()/1000);
    Serial.print(r); 
    Serial.println(F(" sec."));
   
    wdt_reset();
    
    // nacteme cidla
    DS1cidlo.requestTemperatures(); // pozadavek na 1 cidlo
    DS2cidlo.requestTemperatures(); // pozadavek na 2 cidlo
    DS3cidlo.requestTemperatures(); // pozadavek na 3 cidlo
    DS4cidlo.requestTemperatures(); // pozadavek na 4 cidlo
    DS5cidlo.requestTemperatures(); // pozadavek na 5 cidlo
    DS6cidlo.requestTemperatures(); // pozadavek na 6 cidlo

    Serial.print(F("Nacitam teplotu..."));
    teplota[0] = DS1cidlo.getTempCByIndex(0); // teplota z cidla
    teplota[1] = DS2cidlo.getTempCByIndex(0); // teplota z cidla
    teplota[2] = DS3cidlo.getTempCByIndex(0); // teplota z cidla
    teplota[3] = DS4cidlo.getTempCByIndex(0); // teplota z cidla
    teplota[4] = DS5cidlo.getTempCByIndex(0); // teplota z cidla
    teplota[5] = DS6cidlo.getTempCByIndex(0); // teplota z cidla
    Serial.println(F("OK"));
    
    // prevedeme cislo -xx az +xx pro buffer ve formatu status,tis,sto,des,jed
    byte pom = 0;
    
    for(byte q=0; q<6; q++){
      int jed, des, sto, tis, vynasobene;

      // teplota[q] = -123.4; pro test
      
      teplota[q] = teplota[q] * 10; // posuneme desetine misto př: -123.4 na -1234.0

      Serial.print(F("Rozlozena teplota ")); Serial.print(q+1);
       
      if(teplota[q] < 0) {
        vynasobene = abs(teplota[q]); // ziskame kladne cislo ze zaporneho a bude jiz v int misto float
        Serial.print(F(": -"));   
        buffer[pom] = 1;    // 1 = priznak zaporne teploty je mene nez 0C, 0 = neni - teplota
      }
      else {
        vynasobene = teplota[q];
        Serial.print(F(": "));
        buffer[pom] = 0;   // teplota neni zaporna
      }
      
      jed = vynasobene % 10;            // 4
      des = (vynasobene / 10) % 10;     // 3
      sto = (vynasobene / 100) % 10;    // 2
      tis = (vynasobene / 1000) % 10;   // 1  
      Serial.print(tis); Serial.print(sto); Serial.print(des); Serial.print(F(".")); Serial.println(jed);
      
      buffer[pom+4] = jed;             // jednotky 
      buffer[pom+3] = des;             // desitky
      buffer[pom+2] = sto;             // stovky
      buffer[pom+1] = tis;             // tisice  
      pom += 5; // pricteme 5 (kazde cidlo zabere 5 byte a po probehnuti smycky pridame 5+n v indexu bufferu
    }//end for

    Serial.print(F("I2C buffer (0-29)")); 
    for(byte q=0; q<30; q++){
      if(q%5==0)Serial.print(",");
      Serial.print(buffer[q]);
    }//end for
    Serial.println(" ");
    
    pripraveno = true; // dame priznak ze jsou pripravena data k odeslani
   }// end casovac

  if(pom){
    pom=false;
    Serial.print(F("Tik I2C v: ")); Serial.print(last_call); Serial.println(F(" ms."));
  }

 // hlidani zamrznuti I2C sbernice na atmega 328
  if (millis() > (timeout_cal + last_call)) { // hw reset -> vyprsel cas 60 sec pro pozadavek z I2C
    Serial.println(F("Chyba 60 sec!"));
    delay(100);
    software_Reset();
  }
 
}// end loop


void requestEvent(){ // pozadavek z I2C
  // Odesleme data pres i2c spojeni
  if(pripraveno){ // odesleme data pokud jsou v loop pripravena data jinak ne
    Wire.write(buffer, 30); // buffer, 30 byte celkem
    pripraveno = false;
  }
  last_call = millis(); // byl pozadavek z i2c tak nebude restart cpu
  pom=true;
} // end void

void software_Reset(){ // Restarts program from beginning but does not reset the peripherals and registers
  asm volatile ("  jmp 0");  
} // end void
