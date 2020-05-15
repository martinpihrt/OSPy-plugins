/*
Martin Pihrt OSPy plugin - ping tank level
 *  Arduino 1.8.12 pojistky: efuse: 0xFD hfuse: 0xDE lfuse: 0xFF
 *  Atmega 328 16MHz
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
změna 1.2 na 1.3 přidán zpět wdt reset, vlastní I2C knihovna (odolná proti zamrzání), LED bliká dokud se nenaplní průměrování, potom LED svítí
změna 1.1 na 1.2 přidaná podpora pro parallax čidlo (má trig a echo na jednom vodiči), zruseno: pokud neprijde pozadavek z i2c udela se reset
změna 1.0 na 1.1 i2c pozadavek wdt na 30sec (pokud neprijde pozadavek z i2c udela se reset), pokud vše běží jak má, tak led bliká (po 50ms) tj. rychle, jinak sviti.
*/

#define FW "I2C adr: 0x04, FW:1.3, 15.5.2020"  // verze FW na serial
#define ADDRESS 0x04                           // adresa slave I2C

#include <SBWire.h>        // I2C s timeoutem
//#include "Wire.h"        // I2C original Arduino
#include "MedianFilter.h"  // https://github.com/luisllamasbinaburo/Arduino-MedianFilter

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

#define trig_echo_PIN    8          // trig_echo Parallax
#define triggerPIN       2          // trig JSN
#define echoPIN          4          // echo JSN

#define ledPIN 3                    // led 3
#define cal    0                    // kalibrace čidla +- cm pokud je treba

long duration;
unsigned int distance, out, distanceCM;
unsigned int min_probe_val = MIN_probe_val;
unsigned long previousMillis;        // casovac 1 sec
unsigned long previousMillisping;    // casovac 35 msec
unsigned long last_call;             // ms kdy byl I2C pozadavek
unsigned int timeout_cal = 60000;    // za 60 sec bude hw restart pokud neni pozadavek od raspi
volatile boolean pripraveno;         // data jsou pripravena pro I2C k odeslani a muzou se odeslat (ping cm > 0 je to OK)
volatile boolean last_call_OK;       // I2C zadal o data
uint8_t buffer[2];                   // data pro I2C

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
    //Wire.write(buffer, 2);
    Wire.write(buffer,2);
  }
  else{
    buffer[0] = 0;    
    buffer[1] = 0; 
    //Wire.write(buffer, 2);
    Wire.write(buffer,2);
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

  if(currentMillis - previousMillisping >= 35){ // casovac 35ms ping
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
 
 if(currentMillis - previousMillis >= 1000){ // casovac 1000ms pro serial
   previousMillis = currentMillis;
   Serial.print(F("Ping: "));
   Serial.print(distanceCM);
   Serial.print(F(", cal: "));
   if(cal>0)Serial.print(F("+"));
   if(cal<0) Serial.print(F("-"));
   Serial.print(cal);
   Serial.print(F(", out: "));
   Serial.println(out); 

   Serial.print(F("Restart CPU za: "));
   unsigned long r;
   r = (last_call/1000)+(timeout_cal/1000)-(millis()/1000);
   Serial.print(r); 
   Serial.println(F(" sec."));
   Serial.print(F("Tik I2C byl v: ")); Serial.print(last_call); Serial.println(F(" ms."));
   Serial.println(F(""));
 }// end if

 buffer[0] = out >> 8;    // kazdych dalsich 255 prida 1
 buffer[1] = out & 0xff;  // 0-255
    
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
