# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'  

import time
import traceback
import os
import web

from ftplib import FTP     
from threading import Thread, Event

from ospy import helpers
from ospy import version
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string, uptime
from ospy.stations import stations
from ospy.scheduler import scheduler
from ospy.programs import programs
from ospy.options import options
from ospy.options import rain_blocks
from ospy.runonce import run_once
from ospy.inputs import inputs


NAME = 'Remote FTP Control'
MENU =  _('Package: Remote FTP Control')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {'use': False,
     'ftpaddress': 'server@example.cz',
     'ftpname':    'user',
     'ftppass':    'password',
     'loc':        '/',
     }
)       


################################################################################
# Main function loop:                                                          #
################################################################################

class PluginSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()
        
        self.bus = None
        
        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
          time.sleep(1)
          self._sleep_time -= 1

    def run(self):
        log.clear(NAME)    
        try:
            ramdiskpatch = '/home/pi/ramdisk'

            if not os.path.exists(ramdiskpatch): # checking whether there ramdisk
              os.mkdir(ramdiskpatch)
              log.info(NAME, _('Creating ramdisk into') + ': ' + str(ramdiskpatch))
       
        except Exception:
           log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())
                  
        try:
            fstabdata = 'tmpfs       /home/pi/ramdisk    tmpfs    defaults,size=4m    0    0'
            fstabpatch = '/etc/fstab'

            if not fstabdata in open(fstabpatch).read():  # checking and adding a ramdisk to fstab
              log.info(NAME, _('Adding into fstab') + ': ' + str(fstabdata))
              log.info(NAME, _('Saving config to') + ': ' + str(fstabpatch))
              f = open(fstabpatch,"a")  
              f.write(fstabdata)
              f.close()
              # reboot os system
              log.info(NAME, _('Now please restart your operating system!'))

        except Exception:
            log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())
                
        smyckyFTP = 30  
        while not self._stop.is_set():
            try:                    
                if plugin_options['use']:  # if plugin is enabled               
                  if (smyckyFTP > 29):      # every 30 second FTP download and upload
                    smyckyFTP = 0   
                    log.clear(NAME)
                    try:
                        self.ftp = FTP(plugin_options['ftpaddress'], plugin_options['ftpname'], plugin_options['ftppass'])    
                        log.info(NAME, _('FTP connection established.')) 

                        FTP_download(self)  # downloaded from server data.txt and save to ramdisk
                        FTP_upload(self)    # uploaded to the server data stavy.php from the ramdisk

                    except Exception:
                        log.clear(NAME)
                        log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())
                       
                  smyckyFTP += 1 # counter for FTP transmit and reiceive                           
                  
                self._sleep(1)  

            except Exception:
                log.clear(NAME)
                log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())
                self._sleep(60)
                
plugin_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global plugin_sender
    if plugin_sender is None:
        plugin_sender = PluginSender()


def stop():
    global plugin_sender
    if plugin_sender is not None:
        plugin_sender.stop()
        plugin_sender.join()
        plugin_sender = None


def FTP_download(self):     
    try:  # read command file and save to ramdisk   
        self.ftp.retrbinary("RETR " + plugin_options['loc'] + "data.txt" , open("/home/pi/ramdisk/data.txt", 'wb').write) 
        fs = file("/home/pi/ramdisk/data.txt",'r')          
        obsahaut = fs.readline() 
        fs.close()     

        log.debug(NAME, _('FTP received data from file data.txt') + ': ' + str(obsahaut))

        change = False

        if (obsahaut == "AU"):   # scheduller
          options.manual_mode = False        
          log.info(NAME, _('Scheduler mode is activated.'))
          change = True
         
        if (obsahaut == "MA"):   # manual
          options.manual_mode = True       
          log.info(NAME, _('Manual mode is activated.'))
          change = True

        for num_output in range(0,options.output_count):
          s = 'Z' + str(num_output)
          if (obsahaut == s):   # stations xx ON 
             options.manual_mode = True       
             log.info(NAME, _('Manual mode is activated.'))
             stations.activate(num_output)
             log.info(NAME, _('Activated stations') + ': ' + str(num_output + 1))
             change = True
 
          s = 'V' + str(num_output)
          if (obsahaut == s):   # stations xx OFF 
             options.manual_mode = True       
             log.info(NAME, _('Manual mode is activated.'))
             stations.deactivate(num_output)
             log.info(NAME, _('Deactivated stations') + ': ' + str(num_output + 1))
             change = True

        for program in programs.get():
          s = 'P' + str(program.index+1)
          if (obsahaut == s):   # Run-now program xx  
             options.manual_mode = False       
             log.info(NAME, _('Scheduler mode is activated.'))
             programs.run_now(program.index)
             log.info(NAME, _('Activated program') + ': ' + str(program.name))
             self._sleep(2)
             change = True
          program.index+1

        if (obsahaut == "STOP"):   # stop all stations and disable scheduler
            options.scheduler_enabled = False
            programs.run_now_program = None
            run_once.clear()
            log.finish_run(None)
            stations.clear()
            log.info(NAME, _('Stop all stations and disable system.'))
            change = True

        if (obsahaut == "START"):   # enable scheduler
            options.scheduler_enabled = True
            log.info(NAME, _('Enable system.'))
            change = True

        if (change): # delete data.txt command now is OK
          fs= open('/home/pi/ramdisk/data.txt','w')      
          fs.write('OK') 
          fs.close()
          FTP_upload(self) # send to server actual data
       
     
# TODO save_to_options

                                                       
    except Exception: 
      log.clear(NAME)
      log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())
      pass

def FTP_upload(self):   
    try:      
      # create a file "stavy.php" 
      cas = time.strftime('%d.%m.%Y (%H:%M:%S)', time.localtime(time.time())) 
                          
      text = "<?php\r\n$cas = \""                # actual time (ex: cas = dd.mm.yyyy (HH:MM:SS)
      text += cas + "\";\r\n"
      text += "$rain = \'"                 # rain state (ex: rain = 0/1)
      text += str(1 if inputs.rain_sensed() else 0) + "\';\r\n"
      text += "$output = \'"               # use xx outputs count (ex: output = 8)
      text += str(options.output_count) + "\';\r\n"
      text += "$program = \'"              # use xx programs count (ex: program = 3)
      text += str(programs.count()) + "\';\r\n"
   
      text += "$masterstat = "             # master stations index
      for station in stations.get(): 
         if station.is_master:
            text += "\'" + str(station.index) + "\';\r\n"
      if stations.master is None:
         text += "\'\';\r\n"

      text += "$raindel = "                # rain delay
      if rain_blocks.seconds_left():
        m, s = divmod(int(rain_blocks.seconds_left()), 60)
        h, m = divmod(m, 60) 
        text += "\'" + "%dh:%02dm:%02ds" % (h, m, s) + "\';\r\n"
      else:
        text += "\'\';\r\n"
       
      import unicodedata # for only asci text in PHP WEB (stations name, program name...) 

      namestations = []
      for num in range(0,options.output_count): # stations name as array
        namestations.append(unicodedata.normalize('NFKD', stations.get(num).name).encode('ascii','ignore'))
      text += "$name" + " = array"  
      text += str(namestations) + ";\r\n"
 
      statestations = []
      for num in range(0,options.output_count): # stations state as array
        statestations.append(1 if stations.get(num).active else 0)
      text += "$state" + " = array"  
      text += str(statestations) + ";\r\n"

      progrname = []
      for program in programs.get():          # program name as array
        progrname.append(unicodedata.normalize('NFKD', program.name).encode('ascii','ignore'))
      text += "$progname" + " = array"  
      text += str(progrname) + ";\r\n"
 
      text = text.replace('[', '(')  
      text = text.replace(']', ')')

      text += "$schedul = \'"                 # scheduller state (ex: schedul = 0 manual/ 1 scheduler)
      text += str(0 if options.manual_mode else 1) + "\';\r\n"
      text += "$system = \'"                  # scheduller state (ex: system = 0 stop/ 1 scheduler)
      text += str(0 if options.scheduler_enabled else 1) + "\';\r\n"
      text += "$cpu = \'"                     # cpu temp (ex: cpu  = 45.2) 
      text += str(helpers.get_cpu_temp(options.temp_unit)) + "\';\r\n"
      text += "$unit = \'"                    # cpu temp unit(ex: unit  = C/F) in Celsius or Fahrenheit
      text += str(options.temp_unit) + "\';\r\n"
      text += "$ver = \'"                     # software version date (ex: ver  = 2016-07-30)
      text += str(version.ver_date) + "\';\r\n"
      text += "$id = \'"                      # software OSPy ID (ex: id  = "opensprinkler")
      text += str(options.name) + "\';\r\n"
      text += "$ip = \'"                      # OSPy IP address (ex: ip  = "192.168.1.1")
      text += str(helpers.get_ip()) + "\';\r\n"
      text += "$port = \'"                    # OSPy port (ex: port  = "8080")
      text += str(options.web_port) + "\';\r\n"
      text += "$ssl = \'"                     # OSPy use ssl port (ex: ssl  = "1" or "0")
      text += str(1 if options.use_ssl else 0) + "\';\r\n"

      tank = ''
      try:
          from plugins import tank_humi_monitor
          tank = tank_humi_monitor.get_sonic_tank_cm()
          if tank < 0: # -1 is error I2C device for ping not found in tank_humi_monitor
            tank = ''
      except Exception:
        tank = ''

      text = text + "$tank = \'"                    # from tank humi monitor plugins check water level (ex: tank  = "100" in cm or "")
      text = text + str(tank) + "\';\r\n"

      press = ''
      try:
        from plugins import pressure_monitor
        press = pressure_monitor.get_check_pressure()
      except Exception:
        press = ''           

      text = text + "$press = \'"                   # from pressure plugins check press (ex: press  = "1" or "0")
      text = text + str(press) + "\';\r\n"

      ups = ''
      try:
        from plugins import ups_adj
        ups = ups_adj.get_check_power()            # read state power line from plugin ups adj
      except Exception:
        ups = ''           

      text = text + "$ups = \'"                   
      text = text + str(ups) + "\';\r\n"

      result = ''
      finished = [run for run in log.finished_runs() if not run['blocked']]
      if finished:
        result = finished[-1]['start'].strftime('%d-%m-%Y v %H:%M:%S program: ') + finished[-1]['program_name']
      else:
        result = ''

      text = text + "$lastrun = \'"                 # last run program (ex: start d-m-r v h:m:s program: jmemo programu)
      text = text + str(result) + "\';\r\n"

      text = text + "$up = \'"                      # system run uptime
      text = text + str(helpers.uptime()) + "\';\r\n"

      text = text + "?>\r\n"   
      #print text
                          
      """ example php code -----------
      <?php
      $cas = "09.08.2016 (15:28:10)";
      $rain = '0';
      $output = '3';
      $program = '3';
      $masterstat = '0';
      $raindel = '1:26:22'; // hod:min:sec
      $name = array('cerpadlo','test','out2');
      $state = array('0', '0', '0');
      $progname = array('cerpadlo v 5','test','out2');   
      $schedul = '1';
      $system = '1';
      $cpu = '40.1';
      $unit = 'C';
      $ver = '2016-07-30';
      $id = 'Zalevac chata';
      $ip = '192.168.1.253';
      $port = '80';
      $ssl = '1';
      $tank = '20';
      $press = '0';
      $ups = '1';
      $lastrun = '09.08.2016 v 15:28:10 program: bezi 5 minut)';
      $up = '6 days, 0:48:01'
      ?>
      ------------------------------- """                     
  
      try:
        fs=file("/home/pi/ramdisk/stavy.php",'w')      
        fs.write(text) 
        fs.close()

      except:
        log.error(NAME, _('Could not save stavy.php to ramdisk!'))
        pass     

      self.ftp.storbinary("STOR " + plugin_options['loc'] + 'stavy.php'  , open("/home/pi/ramdisk/stavy.php", 'rb'))   
      log.info(NAME, _('Data file stavy.php has send on to FTP server') + ': ' + str(cas))
      
      self.ftp.storbinary("STOR " + plugin_options['loc'] + 'data.txt'  , open("/home/pi/ramdisk/data.txt", 'rb'))   
      log.info(NAME, _('Data file data.txt has send on to FTP server') + ': ' + str(cas))

      self.ftp.close       # FTP end
         
    except Exception:
      log.info(NAME, _('Remote FTP control settings') + ':\n' + traceback.format_exc())


    
################################################################################
# Web pages:                                                                   #
################################################################################


class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.remote_ftp_control(plugin_options, log.events(NAME))

    def POST(self): 
        plugin_options.web_update(web.input())
        if plugin_sender is not None:
          plugin_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)        
