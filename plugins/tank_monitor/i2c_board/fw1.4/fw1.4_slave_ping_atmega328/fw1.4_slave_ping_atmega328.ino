/*
Martin Pihrt OSPy plugin - ping tank level
 *  Arduino 1.8.19 pojistky: efuse: 0xFD hfuse: 0xDE lfuse: 0xFF
 *  Atmega 328 16MHz

Lze pouzit cidla:
a) 4 wire
Ultrazvukový vodotěsný modul pro měření vzdálenosti JSN-SR04T
https://www.banggood.com/cs/SN-SR04T-DC-5V-Ultrasonic-Module-Distance-Meter-Measuring-Transducer-Sensor-IO-Port-Waterproof-p-1376233.html
Jako malá nevýhoda pak může být brána minimální detekovatelná vzdálenost 25 cm nebo poměrně velký detekční úhel.
Measuring range‎: ‎25-400 cm
Measuring angle‎: ‎45-75 degrees
Mounting hole‎: ‎18 mm
V případě, že neměří dobře je nutné otočit ladící trimr (cívku) a doštelovat....
nebo nevodotěsný modul HCSR04
https://rpishop.cz/senzory/815-ultrazvukovy-senzor-hc-sr04.html

b) 3 wire
nevodotěsný modul parallax
https://www.parallax.com/product/28015
Measuring range‎: 3-300 cm

FW
dokud neni nacteno pole prumerovani blikame, jinak svitime LED
změna 1.3 na 1.4 přidán CRC8 součet a odesílání verze FW, zvysen cas casovace z 35ms na 50ms u pingu
změna 1.2 na 1.3 přidán zpět wdt reset, vlastní I2C knihovna (odolná proti zamrzání), LED bliká dokud se nenaplní průměrování, potom LED svítí
změna 1.1 na 1.2 přidaná podpora pro parallax čidlo (má trig a echo na jednom vodiči), zruseno: pokud neprijde pozadavek z i2c udela se reset
změna 1.0 na 1.1 i2c pozadavek wdt na 30sec (pokud neprijde pozadavek z i2c udela se reset), pokud vše běží jak má, tak led bliká (po 50ms) tj. rychle, jinak sviti.
*/

#define FW "I2C adr: 0x04, FW:1.4, 28.06.2022" // verze FW na serial
#define FW_TO_I2C   0x0E                       // 0X0E = dec 14 tj 1.4
#define ADDRESS     0x04                       // adresa slave I2C

#include "SBWire.h"        // I2C s timeoutem
//#include "Wire.h"        // I2C original Arduino
#include "MedianFilter.h"  // https://github.com/luisllamasbinaburo/Arduino-MedianFilter
#include "CRC.h"           // https://github.com/RobTillaart/CRC

#define WDOG               // pokud neni zakomentovane pouzivame watchdog

#ifdef WDOG
   #include <avr/wdt.h>
#endif

//#define PARALLAX_PROBE     // pokud je pouzito 3 dratove cidlo parallax nech odkomentovane, jinak zakomentuj! https://www.parallax.com/product/28015

#ifdef PARALLAX_PROBE 
   #define MIN_probe_val    5       // minimalni vzdalenost od snimace Parallax
#else   
   #define MIN_probe_val    25      // minimalni vzdalenost od snimace JSN
#endif

#define trig_echo_PIN       8       // trig_echo Parallax
#define triggerPIN          2       // trig JSN
#define echoPIN             4       // echo JSN

#define ledPIN              3       // led 3
#define cal                 0       // kalibrace čidla +- cm pokud je treba

long duration;
unsigned int distance, out, distanceCM;
unsigned int min_probe_val = MIN_probe_val;
unsigned long previousMillis;        // casovac 1 sec
unsigned long previousMillisping;    // casovac 50 msec
unsigned long last_call;             // ms kdy byl I2C pozadavek
unsigned int timeout_cal = 60000;    // za 60 sec bude hw restart pokud neni pozadavek od raspi
volatile boolean pripraveno;         // data jsou pripravena pro I2C k odeslani a muzou se odeslat (ping cm > 0 je to OK)
volatile boolean last_call_OK;       // I2C zadal o data
byte buffer[4];                      // data pro I2C

int normal_ping(){
  unsigned long durationMS = 0;       
  digitalWrite(triggerPIN, LOW);
  delayMicroseconds(2);
  digitalWrite(triggerPIN, HIGH);
  delayMicroseconds(20);
  digitalWrite(triggerPIN, LOW);
  durationMS = pulseIn(echoPIN, HIGH, 60000);
  return durationMS/58;  
}

int para_ping(){ // https://www.parallax.com/product/28015
  pinMode(trig_echo_PIN, OUTPUT);
  digitalWrite(trig_echo_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(trig_echo_PIN, HIGH);
  delayMicroseconds(5);
  digitalWrite(trig_echo_PIN, LOW);
  pinMode(trig_echo_PIN, INPUT_PULLUP);
  int duration = pulseIn(trig_echo_PIN, HIGH);
  int cm = microsecondsToCentimeters(duration);
  return cm; // vraci vzdalenost v cm z cidla  
}

long microsecondsToCentimeters(long microseconds){ // pomocna pro ping
   // The speed of sound is 340 m/s or 29 microseconds per centimeter.
   return microseconds/29/2;
}// end long  

void software_Reset(){ // Restarts program from beginning but does not reset the peripherals and registers
  asm volatile ("  jmp 0");  
} // end void  

void requestCallback(){              // i2c pozadavek na data
  last_call_OK = true;               // prisel pozadavek z I2C OK
  
  if(pripraveno){
    Wire.write(buffer, 4);
  }
  else{
    buffer[0] = 255;                   // kazdych dalsich přetečených 255 prida 1
    buffer[1] = 255;                   // 0-255cm 
    buffer[2] = FW_TO_I2C;             // verze FW v CPU
    buffer[3] = 255;                   // CRC
    Wire.write(buffer, 4);
  }  
} //end void 


MedianFilter filter(100,0);  // 100 vzorku na prumerovani

//****************** SETUP **********************
void setup() {
  pinMode(ledPIN, OUTPUT);
  digitalWrite(ledPIN, LOW);
  
  Serial.begin(115200);
  Serial.println(F("OSPy plugin tank monitor"));
  Serial.println(FW);
  delay(1000);

  #ifdef WDOG
     wdt_enable(WDTO_8S);
     wdt_reset();
  #endif

  Wire.begin(ADDRESS);
  Wire.onRequest(requestCallback);  
  
#ifdef PARALLAX_PROBE
  pinMode(trig_echo_PIN, INPUT); 
#else     
  pinMode(triggerPIN, OUTPUT);                  
  pinMode(echoPIN,INPUT_PULLUP);        
#endif

}//end setup

//******************* LOOP **********************
void loop() {
  if(last_call_OK) {
    last_call = millis();
    last_call_OK = false;
  }
  
  wdt_reset();

  unsigned long currentMillis = millis();

  if(currentMillis - previousMillisping >= 50){ // casovac 50ms ping
    previousMillisping = currentMillis;

    if(!pripraveno) digitalWrite(ledPIN, !digitalRead(ledPIN)); // dokud neni nacteno blikame

    #ifdef PARALLAX_PROBE  
      distanceCM = para_ping();
    #else  
      distanceCM = normal_ping();
    #endif  
   
    filter.in(distanceCM+cal); // prumerovani
    out = filter.out();
  }// end if  

 // rozložení pingu 0-400cm na dva bajty
 byte out_0 = out >> 8;                                        // ping nad 255 (posun o 8 bitů)
 byte out_1 = out & 0xff;                                      // ping 0-255 cm
 unsigned int out_sum_01 = out_0 + out_1;                      // výstupní číslo v rozsahu 0-65535 (sečtené bajty 0 a 1) pro vstup do CRC

 // výpočet CRC ze sečtených bajtů 0 a 1
 String s_out_sum = String(out_sum_01);                        // převod int do string jako "0" až "65535"
 unsigned int s_out_len = s_out_sum.length();                  // jak je dlouhy string
 char str[s_out_len];                                          // podle delky vytvorime velke pole 
 s_out_sum.toCharArray(str, s_out_len+1);                      // převod stringu s_out_sum do char pole
 byte* data = (byte*) &str[0];
 byte out_crc = crc8(data, s_out_len, 0x07, 0x00, 0x00, false, false); // výpočet CRC8(array, length, polynome, XORstart, XORend, reverseIn, reverseOut) 
// online test CRC http://zorc.breitbandkatze.de/crc.html
 
 if(currentMillis - previousMillis >= 1000){                   // casovac 1 sec pro tisk na UART
   previousMillis = currentMillis;
   Serial.print(F("Ping:\t"));
   Serial.print(distanceCM);                                   // ping v cm 0-400
   Serial.print(F(", cal:\t"));
   if(cal>0)Serial.print(F("+"));
   if(cal<0) Serial.print(F("-"));
   Serial.print(cal);                                          // případná kalibrace +-cm
   Serial.print(F(", out:\t"));
   Serial.println(out);                                        // výstup ping po průměrování

   Serial.print(F("Vstup do CRC:\t"));
   Serial.print(str);                                          // out ping jako char co jde do CRC8
   Serial.print(F(" ("));
   Serial.print(s_out_len);                                    // jak je dlouhy vstup
   Serial.println(F(" data bytu)"));
   Serial.print(F("CRC8:\t"));
   Serial.print(out_crc);                                      // výtup z CRC8 v dec
   Serial.print(F(" HEX:\t"));
   Serial.println(out_crc, HEX);                               // výstup z CRC8 v hex
   
   Serial.print(F("Restart CPU za: "));
   unsigned long r;
   r = (last_call/1000)+(timeout_cal/1000)-(millis()/1000);
   Serial.print(r); 
   Serial.println(F(" sec."));
   Serial.print(F("Tik I2C byl v:\t")); Serial.print(last_call); Serial.println(F(" ms."));
   Serial.println(F(""));
 }// end if

 buffer[0] = out_0;       // ping kazdych dalsich 255 prida 1 (př: ping = 265, out_0 = 1, out_1 = 10
 buffer[1] = out_1;       // ping 0-255
 buffer[2] = FW_TO_I2C;   // verze FW v CPU
 buffer[3] = out_crc;     // CRC 0-255
    
 if(out > min_probe_val) { // kdyz nejsou data nulova (filtr se naplnil)
    pripraveno = true;     // dame priznak ze jsou pripravena data k odeslani
    digitalWrite(ledPIN, HIGH);
 }
 else {
    pripraveno = false;
 }	

 // hlidani zamrznuti I2C sbernice na atmega 328
 if (millis() > (timeout_cal + last_call)) { // hw reset -> vyprsel cas 60 sec pro pozadavek z I2C
    Serial.println(F(""));
    Serial.println(F("Chyba 60 sec!"));
    delay(100);
    software_Reset();
 }//end if

}//end loop
