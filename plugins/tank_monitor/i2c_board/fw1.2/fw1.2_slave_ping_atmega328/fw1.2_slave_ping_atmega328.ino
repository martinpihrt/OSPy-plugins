/*
10.4.2020
* 25.2.2020 Martin Pihrt OSPy plugin
 *  Arduino 1.8.12
 *  
Lze pouzit:
a) 4 wire
Ultrazvukový vodotěsný modul pro měření vzdálenosti JSN-SR04T
https://www.banggood.com/cs/SN-SR04T-DC-5V-Ultrasonic-Module-Distance-Meter-Measuring-Transducer-Sensor-IO-Port-Waterproof-p-1376233.html
Jako malá nevýhoda pak může být brána minimální detekovatelná vzdálenost 25 cm nebo poměrně velký detekční úhel.
Measuring range‎: ‎25-450 cm
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
změna 1.1 na 1.2 přidaná podpora pro parallax čidlo (má trig a echo na jednom vodiči), zruseno: pokud neprijde pozadavek z i2c udela se reset
změna 1.0 na 1.1 i2c pozadavek wdt na 30sec (pokud neprijde pozadavek z i2c udela se reset), pokud vše běží jak má, tak led bliká (po 50ms) tj. rychle, jinak sviti.
*/

#include <Wire.h>          // I2C
#include "MedianFilter.h"  // https://github.com/luisllamasbinaburo/Arduino-MedianFilter
#include <avr/wdt.h>       // watchdog

//#define PARALLAX_PROBE     // pokud je pouzito 3 dratove cidlo parallax nech odkomentovane, jinak zakomentuj! https://www.parallax.com/product/28015

#ifdef PARALLAX_PROBE
   #define trig_echo_PIN    8       // trig_echo parallax
   #define MIN_probe_val    5       // minimalni vzdalenost od snimace
#else   
   #define triggerPIN       2       // trig
   #define echoPIN          4       // echo
   #define MIN_probe_val    25      // minimalni vzdalenost od snimace
#endif

#define ledPIN 3           // led 3

#define cal    0           // kalibrace čidla +- cm pokud je treba

#define ADDRESS 0x04       // adresa slave I2C

long duration;
unsigned int distance, out, distanceCM;
unsigned int min_probe_val = MIN_probe_val;

unsigned long previousMillis; 


uint8_t buffer[2];
   

void requestCallback(){     // i2c mereni
  Wire.write(buffer, 2);
} //end void 


MedianFilter filter(100,0);  // 100 vzorku na prumerovani

//****************** SETUP **********************
void setup() {
  Wire.begin(ADDRESS);
  Wire.onRequest(requestCallback);
  
#ifdef PARALLAX_PROBE
  pinMode(trig_echo_PIN, INPUT); 
#else     
  pinMode(triggerPIN, OUTPUT);                  
  pinMode(echoPIN,INPUT_PULLUP);        
#endif

  Serial.begin(115200);
  pinMode(ledPIN, OUTPUT);
  digitalWrite(ledPIN, LOW);
  wdt_enable(WDTO_4S);   // watchdog 4s
}

//******************* LOOP **********************
void loop() {

#ifdef PARALLAX_PROBE  
  distanceCM = para_ping();
#else  
  distanceCM = normal_ping();
#endif  

  filter.in(distanceCM+cal); // prumerovani
  out = filter.out();
  
 unsigned long currentMillis = millis();
 
 if(currentMillis - previousMillis >= 1000){ // casovac na serial
   previousMillis = currentMillis;
   Serial.print(F("ping: "));
   Serial.print(distanceCM);
   Serial.print(F(", cal: "));
   if(cal>0)Serial.print(F("+"));
   if(cal<0) Serial.print(F("-"));
   Serial.print(cal);
   Serial.print(F(", out: "));
   Serial.println(out); 
 }

 buffer[0] = out >> 8;    // kazdych dalsich 255 prida 1
 buffer[1] = out & 0xff;  // 0-255
    
 if(out > min_probe_val) { // kdyz nejsou data nulova (filtr se naplnil)
    digitalWrite(ledPIN, HIGH);
 }
 else {
    digitalWrite(ledPIN, LOW);
 }	

 delay(10);
 wdt_reset(); 
}//end loop

int normal_ping(){
  unsigned long durationMS = 0;       
  #ifndef PARALLAX_PROBE
     digitalWrite(triggerPIN, LOW);
     delayMicroseconds(2);
     digitalWrite(triggerPIN, HIGH);
     delayMicroseconds(20);
     digitalWrite(triggerPIN, LOW);
     durationMS = pulseIn(echoPIN, HIGH, 60000);
     return durationMS/58;
  #endif   
}

int para_ping(){ // https://www.parallax.com/product/28015
  #ifdef PARALLAX_PROBE
     pinMode(trig_echo_PIN, OUTPUT);
     digitalWrite(trig_echo_PIN, LOW);
     delayMicroseconds(2);
     digitalWrite(trig_echo_PIN, HIGH);
     delayMicroseconds(5);
     digitalWrite(trig_echo_PIN, LOW);
     pinMode(trig_echo_PIN, INPUT);
     int duration = pulseIn(trig_echo_PIN, HIGH);
     int cm = microsecondsToCentimeters(duration);
     return cm; // vraci vzdalenost v cm z cidla
  #endif   
}

long microsecondsToCentimeters(long microseconds){ // pomocna pro ping
   // The speed of sound is 340 m/s or 29 microseconds per centimeter.
   return microseconds/29/2;
}// end long  
