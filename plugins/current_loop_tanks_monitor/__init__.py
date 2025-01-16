# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt' # www.pihrt.com

import json
import time
import datetime

import sys
import traceback
import os

from threading import Thread, Event

import web
import smbus

from ospy import helpers
from ospy.options import options, rain_blocks
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

from ospy.webpages import pluginScripts # Inject javascript to call our API for data and modify the display (in base.html)
from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

pluginScripts.append("current_loop_tanks_monitor/script/tank.js")

NAME = 'Current Loop Tanks Monitor'
MENU =  _('Package: Current Loop Tanks Monitor')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {   # tanks 
        'label1':  _('Tank 1'),                  # label for tank 1 - 4
        'label2':  _('Tank 2'),
        'label3':  _('Tank 3'),
        'label4':  _('Tank 4'),
        'en_tank1': True,                        # enabling or disabling tank 1 - 4
        'en_tank2':False,
        'en_tank3': False,
        'en_tank4': False,
        'maxHeightCm1': 400,                     # maximal water height for measuring tank 1 - 4 (in cm)
        'maxHeightCm2': 400,
        'maxHeightCm3': 400,
        'maxHeightCm4': 400,
        'maxVolume1': 3000,                      # max volume in the tank 1 - 4 (in liters)
        'maxVolume2': 3000,
        'maxVolume3': 3000,
        'maxVolume4': 3000,
        'minVolt1': 0.0,                         # AIN0 min input value for 4mA
        'minVolt2': 0.0,                         # AIN0 min input value
        'minVolt3': 0.0,                         # AIN0 min input value
        'minVolt4': 0.0,                         # AIN0 min input value
        'maxVolt1': 4.096,                       # AIN0 max input value for 20mA
        'maxVolt2': 4.096,                       # AIN1 max input value
        'maxVolt3': 4.096,                       # AIN2 max input value
        'maxVolt4': 4.096,                       # AIN3 max input value
        'i2c': 0,                                # I2C for ADC converter ADS1115 (0x48 default)
        'use_footer': False,
        # logs
        'en_sql_log': False,                     # logging to sql database
        'en_log': False,                         # logging to local json file
        'type_log': 0,                           # 0 = show log and graph from local log file, 1 = from database
        'log_interval': 1,                       # interval for log in minutes
        'log_records': 0,                        # the number of records (0 = unlimited)
        'dt_from' : '2024-01-01T00:00',          # for graph history (from date time ex: 2024-02-01T6:00)
        'dt_to' : '2024-01-01T00:00',            # for graph history (to date time ex: 2024-03-17T12:00)
        # e-mail notifications
        'en_eml_tank1_low': False,               # send e-mail if water in tank 1 is LOW
        'en_eml_tank2_low': False,               # send e-mail if water in tank 2 is LOW
        'en_eml_tank3_low': False,               # send e-mail if water in tank 3 is LOW
        'en_eml_tank4_low': False,               # send e-mail if water in tank 4 is LOW
        'eml_tank1_low_lvl': 20,                 # min level in % tank 1 for threshold and send e-mail
        'eml_tank2_low_lvl': 20,                 # min level in % tank 2 for threshold and send e-mail
        'eml_tank3_low_lvl': 20,                 # min level in % tank 3 for threshold and send e-mail
        'eml_tank4_low_lvl': 20,                 # min level in % tank 4 for threshold and send e-mail
        'eml_tank1_high_lvl': 40,                # level in % tank 1 for release threshold and send e-mail
        'eml_tank2_high_lvl': 40,                # level in % tank 2 for release threshold and send e-mail
        'eml_tank3_high_lvl': 40,                # level in % tank 3 for release threshold and send e-mail
        'eml_tank4_high_lvl': 40,                # level in % tank 4 for release threshold and send e-mail
        'eml_subject_1': _('Report from OSPy: Tank 1 has minimal level!'),
        'eml_subject_2': _('Report from OSPy: Tank 2 has minimal level!'),
        'eml_subject_3': _('Report from OSPy: Tank 3 has minimal level!'),
        'eml_subject_4': _('Report from OSPy: Tank 4 has minimal level!'),
    }
)

# Registers and cmd for ADS1115
ADS1115_CONVERSION_REG = 0x00
ADS1115_CONFIG_REG = 0x01

# Mode setting for independent channels (single-ended) AIN0 to AIN3
CONFIG_GAIN = 0x0200  # Gain 1 (range ±4.096V)
CONFIG_MODE = 0x0100  # Mode: single-shot

tanks = {}
tanks['levelCm']        = [0, 0, 0, 0]
tanks['volumeLiter']    = [0, 0, 0, 0]
tanks['levelPercent']   = [0, 0, 0, 0]
tanks['voltage']        = [0, 0, 0, 0]
tanks['label']          = [plugin_options['label1'], plugin_options['label2'], plugin_options['label3'], plugin_options['label4']]


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    global tanks

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0
        tanks['label']   = [plugin_options['label1'], plugin_options['label2'], plugin_options['label3'], plugin_options['label4']]

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        tank_mon = None
        last_millis = int(round(time.time() * 1000))                            # timer for saving log
        last_millis_2 = int(round(time.time() * 1000))                          # timer for periodic measuring
        send_eml = [0,0,0,0]                                                    # status for sending e-mails from tank 1-4
        eml_refresh = [1,1,1,1]                                                 # status for release sending e-mails from tank 1-4
        first_wait = True                                                       # waiting on first measure (blocking send email after power on)
        get_data()
        self._sleep(1)
        get_data()        

        if plugin_options['use_footer']:
            tank_mon = showInFooter()                                           # instantiate class to enable data in footer
            tank_mon.button = "current_loop_tanks_monitor/settings"             # button redirect on footer
            tank_mon.label =  _('Tanks')                                        # label on footer

        while not self._stop_event.is_set():
            try:
                millis = int(round(time.time() * 1000))
    
                ### periodically measuring after 5 seconds
                if (millis - last_millis_2) >= 5000:
                    last_millis_2 = millis
                    log.clear(NAME)
                    get_data()

                ### periodically logging (xx minute interval)
                if plugin_options['en_log'] or plugin_options['en_sql_log']:
                    interval = (plugin_options['log_interval'] * 60000)
                    if (millis - last_millis) >= interval:
                       last_millis = millis
                       update_log()

                for i in range(4):
                    ### check water level is lower than the set minimum for e-mails
                    if plugin_options['en_eml_tank{}_low'.format(i+1)] and not send_eml[i] and eml_refresh[i]:  # is enabled sendig e-mail and refresh is true and not sending
                        if tanks['levelPercent'][i] <= plugin_options['eml_tank{}_low_lvl'.format(i+1)]:        # level in tank xx < eml_tankXX_low_lvl
                            send_eml[i] = True
                            eml_refresh[i] = False

                    ### check water level is higher than the set minimum and release for e-mails
                    if plugin_options['en_eml_tank{}_low'.format(i+1)] and not eml_refresh[i]:                  # is enabled sendig e-mail and not refresh
                        if tanks['levelPercent'][i] >= plugin_options['eml_tank{}_high_lvl'.format(i+1)]:       # level in tank xx > eml_tankXX_high_lvl for release
                            eml_refresh[i] = True

                    ### send e-mail
                    if send_eml[i] and not first_wait:
                        try:
                            try_mail = None
                            from plugins.email_notifications_ssl import try_mail
                            if try_mail is not None:
                                msg = '<b>' + _('Current Loop Tanks Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: Water Tank has minimum Water Level') +  ': ' + str(plugin_options['eml_tank{}_low_lvl'.format(i+1)]) + _('%') + '.\n' + '</p>'
                                msglog = _('Current Loop Tanks Monitor plug-in') + ': ' + _('System detected error: Water Tank has minimum Water Level') +  ': {}'.format(plugin_options['eml_tank{}_low_lvl'.format(i+1)]) + _('%') + '. '  
                                try_mail(msg, msglog, attachment=None, subject=plugin_options['eml_subject_{}'.format(i+1)]) # try_mail(text, logtext, attachment=None, subject=None)
                        except Exception:
                            log.info(NAME, _('E-mail not send! The Email Notifications plug-in is not found in OSPy or not correctly setuped.'))
                            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())

                        send_eml[i] = False

                ### footer on homepage
                if plugin_options['use_footer']:
                    if tank_mon is not None:
                        tempText = ""
                        if plugin_options['en_tank1']: 
                            tempText += '{} {} % {} l '.format(tanks['label'][0], round(tanks['levelPercent'][0]), round(tanks['volumeLiter'][0]))
                        if plugin_options['en_tank2']: 
                            tempText += '{} {} % {} l '.format(tanks['label'][1], round(tanks['levelPercent'][1]), round(tanks['volumeLiter'][1]))
                        if plugin_options['en_tank3']: 
                            tempText += '{} {} % {} l '.format(tanks['label'][2], round(tanks['levelPercent'][2]), round(tanks['volumeLiter'][2]))
                        if plugin_options['en_tank4']: 
                            tempText += '{} {} % {} l '.format(tanks['label'][3], round(tanks['levelPercent'][3]), round(tanks['volumeLiter'][3]))
                        if not plugin_options['en_tank1'] and not plugin_options['en_tank2'] and not plugin_options['en_tank3'] and not plugin_options['en_tank4']:
                            tempText = _('The measurement of all tanks is switched off.')
                        tank_mon.val = tempText.encode('utf8').decode('utf8')

                self._sleep(1)
                first_wait = False

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()


def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None


def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
            time.sleep(0.1)
        else:
            break

    if not tries:
        raise error

    return result


# Functions to read ADC on a specific channel
def read_adc(bus, channel):
    if channel == 0:
        config = 0x4000  # AIN0 single-ended
    elif channel == 1:
        config = 0x5000  # AIN1 single-ended
    elif channel == 2:
        config = 0x6000  # AIN2 single-ended
    elif channel == 3:
        config = 0x7000  # AIN3 single-ended
    else:
        raise ValueError(_('Error: Invalid channel.'))

    config |= CONFIG_GAIN | CONFIG_MODE | 0x8000  # Start single-conversion
    
    
    i2c_adr_list = [0x48, 0x49, 0x4A, 0x4B]
    i2c_adr = i2c_adr_list[plugin_options["i2c"]]

    # Write config to ADS1115
    try:
        bus.write_i2c_block_data(i2c_adr, ADS1115_CONFIG_REG, [(config >> 8) & 0xFF, config & 0xFF])
    except IOError:
        raise IOError(_('Error: No I2C bus or ADC available on address 0x48, 0x49, 0x4A, 0x4B.'))

    # Waiting for the conversion to complete
    time.sleep(0.2)
    
    # Reading the result from the conversion register
    try:
        result = bus.read_i2c_block_data(i2c_adr, ADS1115_CONVERSION_REG, 2)
    except IOError:
        raise IOError(_('Error: It is not possible to read data from the AD converter.'))

    raw_adc = (result[0] << 8) | result[1]
    
    # Convert to voltage range if the result exceeds 16bit
    if raw_adc > 0x7FFF:
        raw_adc -= 0x10000
    
    # Converting ADC value to voltage
    voltage = raw_adc * 4.096 / 32768.0  # ±4.096V range, 16bit convert
    
    return round(voltage if voltage > 0 else 0, 3)  # return positive voltage or 0


def get_data():
    global tanks

    try:
        bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)
    except FileNotFoundError:
        log.error(NAME, _('Error: the I2C bus is not available.'))
        return
    
    # Definition for the tank level for each channel (minimum and maximum voltage)
    LEVEL_DEFINITIONS = {
        0: {"min": plugin_options['minVolt1'], "max": plugin_options['maxVolt1']},  # AIN0
        1: {"min": plugin_options['minVolt2'], "max": plugin_options['maxVolt2']},  # AIN1
        2: {"min": plugin_options['minVolt3'], "max": plugin_options['maxVolt3']},  # AIN2
        3: {"min": plugin_options['minVolt4'], "max": plugin_options['maxVolt4']}   # AIN3
    }

    MAX_DEFINITION = {
        0: {"max": plugin_options['maxHeightCm1'], "maxVol": plugin_options['maxVolume1']},
        1: {"max": plugin_options['maxHeightCm2'], "maxVol": plugin_options['maxVolume2']},
        2: {"max": plugin_options['maxHeightCm3'], "maxVol": plugin_options['maxVolume3']},
        3: {"max": plugin_options['maxHeightCm4'], "maxVol": plugin_options['maxVolume4']},
    }

    # Reading all four channels
    IO_error = False
    VAL_error = False
    adc_values = []

    for channel in range(4):
        try:
            adc_value = try_io(lambda: read_adc(bus, channel))
            adc_values.append(adc_value)
            
            # Voltage conversion to tank level for the current channel
            min_voltage = LEVEL_DEFINITIONS[channel]["min"]
            max_voltage = LEVEL_DEFINITIONS[channel]["max"]

            level_percentage = voltage_to_level(adc_value, min_voltage, max_voltage)
            level_cm = level_to_cm(level_percentage, MAX_DEFINITION[channel]["max"])
            volume_liter = (level_cm / MAX_DEFINITION[channel]["max"]) * MAX_DEFINITION[channel]["maxVol"]

            tanks['voltage'][channel] = adc_value
            tanks['levelPercent'][channel] = level_percentage
            tanks['levelCm'][channel] = level_cm
            tanks['volumeLiter'][channel] = volume_liter

        except ValueError as ve:
            VAL_error = True
            #log.error(NAME, _('Error for channel {}: {}.').format(channel, ve))

        except IOError as ioe:
            IO_error = True
            #log.error(NAME, _('I/O error for channel {}: {}.').format(channel, ioe))

    if IO_error:    
        log.error(NAME, _('Error: I/O.'))

    if VAL_error:
        log.error(NAME, _('Error: ADC value.'))

    if not IO_error and not VAL_error:
        log.info(NAME, _('No problems (measurement works as it should).'))


def scan_i2c():
    bus = None
    try:
        bus = smbus.SMBus(1)
    except FileNotFoundError:
       log.error(NAME, _('Error: I2C bus is not available.'))
       return []

    devices = []
    for address in range(128):
        try:
            bus.write_byte(address, 0)
            devices.append(hex(address))
        except OSError:
            pass
    if devices:
        #log.info(NAME, _('I2C devices found at the following addresses: {}.').format(devices))
        return devices
    else:
        log.error(NAME, _('No I2C device was found.'))
        return []


def voltage_to_level(voltage, min_voltage, max_voltage):
    if voltage < min_voltage:
        return 0.0
    elif voltage > max_voltage:
        return 100.0
    else:
        return (voltage - min_voltage) / (max_voltage - min_voltage) * 100.0


def level_to_cm(level, maxHeightCm):
    # Makes sure the level is in the range 0-100
    level = max(0, min(level, 100))
    # Calculation of the level in centimeters from the percentage
    return (level / 100) * maxHeightCm


def write_graph_log(json_data):
    """Write data to graph json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def create_default_graph():
    """Create default graph json file."""

    graph_data = [
        {"station": '{} %'.format(plugin_options['label1']), "balances": {}},
        {"station": '{} %'.format(plugin_options['label2']), "balances": {}}, 
        {"station": '{} %'.format(plugin_options['label3']), "balances": {}},
        {"station": '{} %'.format(plugin_options['label4']), "balances": {}},
        {"station": '{} l'.format(plugin_options['label1']), "balances": {}},
        {"station": '{} l'.format(plugin_options['label2']), "balances": {}},
        {"station": '{} l'.format(plugin_options['label3']), "balances": {}},
        {"station": '{} l'.format(plugin_options['label4']), "balances": {}},                        
    ]
    write_graph_log(graph_data)
#    log.debug(NAME, _('Create default graph json file.'))


def write_log(json_data):
    """Write data to log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def read_graph_log():
    """Read graph data from json file."""
    data = []

    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass
    return data


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()
 
        graph_data = [
            {"station": '{} %'.format(plugin_options['label1']), "balances": {}},
            {"station": '{} %'.format(plugin_options['label2']), "balances": {}}, 
            {"station": '{} %'.format(plugin_options['label3']), "balances": {}},
            {"station": '{} %'.format(plugin_options['label4']), "balances": {}},
            {"station": '{} l'.format(plugin_options['label1']), "balances": {}},
            {"station": '{} l'.format(plugin_options['label2']), "balances": {}},
            {"station": '{} l'.format(plugin_options['label3']), "balances": {}},
            {"station": '{} l'.format(plugin_options['label4']), "balances": {}},                        
        ]

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is tank 1, tank 2 ...
                epoch = int(datetime.datetime.timestamp(row[1]))

                tmp0 = graph_data[0]['balances']
                tank1 = {'total': row[2]}
                tmp0.update({epoch: tank1})

                tmp1 = graph_data[1]['balances']
                tank2 = {'total': row[3]}
                tmp1.update({epoch: tank2})

                tmp2 = graph_data[2]['balances']
                tank3 = {'total': row[4]}
                tmp2.update({epoch: tank3})

                tmp3 = graph_data[3]['balances']
                tank4 = {'total': row[5]}
                tmp3.update({epoch: tank4})

                tmp0 = graph_data[4]['balances']
                tank1 = {'total': row[6]}
                tmp0.update({epoch: tank1})

                tmp1 = graph_data[5]['balances']
                tank2 = {'total': row[7]}
                tmp1.update({epoch: tank2})

                tmp2 = graph_data[6]['balances']
                tank3 = {'total': row[8]}
                tmp2.update({epoch: tank3})

                tmp3 = graph_data[7]['balances']
                tank4 = {'total': row[9]}
                tmp3.update({epoch: tank4})

        data = graph_data

    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass
    return data


def read_log():
    """Read log data from json file."""
    data = []
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass
    return data


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM `currentmonitor` ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,tank1,tank2,tank3,tank4
    except:
        log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
        pass
    return data


def update_log():
    """Update data in json files."""
    global tanks

    if plugin_options['en_log']:
        ### Data for log ###
        try:
            log_data = read_log()
        except:
            write_log([])
            log_data = read_log()

        from datetime import datetime

        data = {'datetime': datetime_string()}
        data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
        data['time'] = str(datetime.now().strftime('%H:%M:%S'))
        data['tank1'] = str(round(tanks['levelPercent'][0]))
        data['tank2'] = str(round(tanks['levelPercent'][1]))
        data['tank3'] = str(round(tanks['levelPercent'][2]))
        data['tank4'] = str(round(tanks['levelPercent'][3]))
        data['tank1vol'] = str(round(tanks['volumeLiter'][0]))
        data['tank2vol'] = str(round(tanks['volumeLiter'][1]))
        data['tank3vol'] = str(round(tanks['volumeLiter'][2]))
        data['tank4vol'] = str(round(tanks['volumeLiter'][3]))

        log_data.insert(0, data)
        if plugin_options['log_records'] > 0:
            log_data = log_data[:plugin_options['log_records']]

        try:
            write_log(log_data)
        except:
            write_log([])

        ### Data for graph log ###
        try:
            graph_data = read_graph_log()
        except:
            create_default_graph()
            graph_data = read_graph_log()
#            log.debug(NAME, _('Create default graph json file.'))

        timestamp = int(time.time())

        try:
            tmp0 = graph_data[0]['balances']
            tank1 = {'total': round(tanks['levelPercent'][0])} # percent tank 1
            tmp0.update({timestamp: tank1})

            tmp1 = graph_data[1]['balances']
            tank2 = {'total': round(tanks['levelPercent'][1])}
            tmp1.update({timestamp: tank2})

            tmp2 = graph_data[2]['balances']
            tank3 = {'total': round(tanks['levelPercent'][2])}
            tmp2.update({timestamp: tank3})

            tmp3 = graph_data[3]['balances']
            tank4 = {'total': round(tanks['levelPercent'][3])} # percent tank 4
            tmp3.update({timestamp: tank4})

            tmp0 = graph_data[4]['balances']
            tank1 = {'total': round(tanks['volumeLiter'][0])}  # volume tank 1
            tmp0.update({timestamp: tank1})

            tmp1 = graph_data[5]['balances']
            tank2 = {'total': round(tanks['volumeLiter'][1])}
            tmp1.update({timestamp: tank2})

            tmp2 = graph_data[6]['balances']
            tank3 = {'total': round(tanks['volumeLiter'][2])}
            tmp2.update({timestamp: tank3})

            tmp3 = graph_data[7]['balances']
            tank4 = {'total': round(tanks['volumeLiter'][3])}  # volume tank 4
            tmp3.update({timestamp: tank4})

            write_graph_log(graph_data)
#            log.info(NAME, _('Saving to graph log files.'))
        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
            create_default_graph()

    if plugin_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db
            # first create table tankmonitor if not exists
            sql = "CREATE TABLE IF NOT EXISTS `currentmonitor` (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, tank1 VARCHAR(4), tank2 VARCHAR(4), tank3 VARCHAR(4), tank4 VARCHAR(4), tank1vol VARCHAR(4), tank2vol VARCHAR(4), tank3vol VARCHAR(4), tank4vol VARCHAR(4))"
            execute_db(sql, test=False, commit=False) # not commit
            # next insert data to table tankmonitor
            sql = "INSERT INTO `currentmonitor` (`tank1`, `tank2`, `tank3`, `tank4`, `tank1vol`, `tank2vol`, `tank3vol`, `tank4vol`) VALUES ('%s','%s','%s','%s','%s','%s','%s','%s')" % (round(tanks['levelPercent'][0]),round(tanks['levelPercent'][1]),round(tanks['levelPercent'][2]),round(tanks['levelPercent'][3]),round(tanks['volumeLiter'][0]),round(tanks['volumeLiter'][1]),round(tanks['volumeLiter'][2]),round(tanks['volumeLiter'][3]))
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
#            log.debug(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for tank."""

    def GET(self):
        global sender
        i2c = None
        qdict = web.input()
        log_now = helpers.get_input(qdict, 'log_now', False, lambda x: True)
        find_i2c = helpers.get_input(qdict, 'find_i2c', False, lambda x: True)

        if sender is not None and log_now:
            update_log()
            return self.plugin_render.current_loop_tanks_monitor(plugin_options, i2c)

        if sender is not None and find_i2c:
            found = scan_i2c()
            i2c_adr_list = ['0x48', '0x49', '0x4A', '0x4B']
            matching_addresses = [address for address in found if address in i2c_adr_list]
            if matching_addresses:
                i2c = " ".join(matching_addresses)
            else:
                i2c = _('Not found at any known addresses: 0x48, 0x49, 0x4A, 0x4B')                
            return self.plugin_render.current_loop_tanks_monitor(plugin_options, i2c)

        # switch 1-4 on plugin homepage in tank (on-off for tanks)
        for i in range(1, 4):
            if sender is not None:
                if 'en_tank{}'.format(i) in qdict:
                    if qdict['en_tank{}'.format(i)] == 'on':
                        plugin_options.__setitem__('en_tank{}'.format(i), True)
                    if qdict['en_tank{}'.format(i)] == 'off':
                        plugin_options.__setitem__('en_tank{}'.format(i), False)

        return self.plugin_render.current_loop_tanks_monitor(plugin_options, i2c)

    def POST(self):
        i2c = None
        return self.plugin_render.current_loop_tanks_monitor(plugin_options, i2c)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_help()


class graph_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        global sender
        qdict  = web.input()
        delfilter = helpers.get_input(qdict, 'delfilter', False, lambda x: True)
        
        if sender is not None and 'dt_from' in qdict and 'dt_to' in qdict:
            dt_from = qdict['dt_from']
            dt_to = qdict['dt_to']
            plugin_options.__setitem__('dt_from', dt_from) #__setitem__(self, key, value)
            plugin_options.__setitem__('dt_to', dt_to)     #__setitem__(self, key, value)

        if sender is not None and delfilter:
            from datetime import datetime, timedelta
            dt_now = (datetime.today() + timedelta(days=1)).date()
            plugin_options.__setitem__('dt_from', "2020-01-01T00:00")
            plugin_options.__setitem__('dt_to', "{}T00:00".format(dt_now))

        return self.plugin_render.current_loop_tanks_monitor_graph(plugin_options)


class graph_json(ProtectedPage):
    """Load an json data for graph"""

    def GET(self):
        data = []
        try:
            from datetime import datetime

            dt_from = datetime.strptime(plugin_options['dt_from'], '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(plugin_options['dt_to'], '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())

            json_data = [{}]

            try:
                if plugin_options['type_log'] == 0:
                    json_data = read_graph_log()
                if plugin_options['type_log'] == 1:
                    json_data = read_graph_sql_log()
            except:
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                pass

            if len(json_data) > 0:  
                for i in range(8):                                                 # 0=tank1 %, 1=tank2 %, 2=tank3 %, 3=tank4 %, 4=tank1 liter, 5=tank2 l, 6=tank3 l, 7=tank4 l
                    temp_balances = {}
                    for key in json_data[i]['balances']:
                        try:
                            find_key = int(key.encode('utf8'))                     # key is in unicode ex: u'1601347000' -> find_key is int number
                        except:
                            find_key = key      
                        if find_key >= log_start and find_key <= log_end:          # timestamp interval from <-> to
                            temp_balances[key] = json_data[i]['balances'][key]    
                    data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)


class log_page(ProtectedPage):
    """Load an html page for log"""

    def GET(self):
        global sender
        qdict  = web.input()
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)

        if sender is not None and delSQL:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `currentmonitor`"
                execute_db(sql, test=False, commit=False)  
#                log.info(NAME, _('Deleting the currentmonitor table from the database.'))
            except:
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                pass

        if sender is not None and delete:
            write_log([])
            create_default_graph()
            raise web.seeother(plugin_url(log_page), True)
                
        return self.plugin_render.current_loop_tanks_monitor_log(read_log(), read_sql_log(), plugin_options)


class setup_page(ProtectedPage):
    """Load an html page for setup"""

    def GET(self):
        global sender
        qdict  = web.input()
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)

        if sender is not None and delSQL:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `currentmonitor`"
                execute_db(sql, test=False, commit=False)  
#                log.debug(NAME, _('Deleting the currentmonitor table from the database.'))
            except:
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                pass

        return self.plugin_render.current_loop_tanks_monitor_setup(plugin_options, log.events(NAME)) 

    def POST(self):
        global sender

        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()

#        log.debug(NAME, _('Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True)


class data_json(ProtectedPage):
    """Returns tank data in JSON format."""
    global tanks

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}

        try:
            data =  {
                'tank1': { 'label': plugin_options['label1'], 'maxHeightCm': plugin_options['maxHeightCm1'], 'maxVolume':  plugin_options['maxVolume1'], 'level': round(tanks['levelCm'][0]), 'voltage': round(tanks['voltage'][0],3) },
                'tank2': { 'label': plugin_options['label2'], 'maxHeightCm': plugin_options['maxHeightCm2'], 'maxVolume':  plugin_options['maxVolume2'], 'level': round(tanks['levelCm'][1]), 'voltage': round(tanks['voltage'][1],3) },
                'tank3': { 'label': plugin_options['label3'], 'maxHeightCm': plugin_options['maxHeightCm3'], 'maxVolume':  plugin_options['maxVolume3'], 'level': round(tanks['levelCm'][2]), 'voltage': round(tanks['voltage'][2],3) },
                'tank4': { 'label': plugin_options['label4'], 'maxHeightCm': plugin_options['maxHeightCm4'], 'maxVolume':  plugin_options['maxVolume4'], 'level': round(tanks['levelCm'][3]), 'voltage': round(tanks['voltage'][3],3) },
                'msg': log.events(NAME)
            }
        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())

        return json.dumps(data)


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            log_file = read_log()
            data  = "Date/Time"
            data += "; Date"
            data += "; Time"
            data += "; {} %".format(plugin_options['label1'])
            data += "; {} %".format(plugin_options['label2'])
            data += "; {} %".format(plugin_options['label3'])
            data += "; {} %".format(plugin_options['label4'])
            data += "; {} l".format(plugin_options['label1'])
            data += "; {} l".format(plugin_options['label2'])
            data += "; {} l".format(plugin_options['label3'])
            data += "; {} l".format(plugin_options['label4'])
            data += '\n'

            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    interval['date'],
                    interval['time'],
                    '{}'.format(interval['tank1']),
                    '{}'.format(interval['tank2']),
                    '{}'.format(interval['tank3']),
                    '{}'.format(interval['tank4']),
                    '{}'.format(interval['tank1vol']),
                    '{}'.format(interval['tank2vol']),
                    '{}'.format(interval['tank3vol']),
                    '{}'.format(interval['tank4vol']),
                ]) + '\n'

        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'local_log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types 
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data


class log_sql_csv(ProtectedPage):  # save log file from database as csv file type from web
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            from plugins.database_connector import execute_db
            sql = "SELECT * FROM `currentmonitor`"
            log_file = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,tank1,2,3,4 in % and liter
            data  = "Id"
            data += "; Date/Time"
            data += "; {} %".format(plugin_options['label1'])
            data += "; {} %".format(plugin_options['label2'])
            data += "; {} %".format(plugin_options['label3'])
            data += "; {} %".format(plugin_options['label4'])
            data += "; {} l".format(plugin_options['label1'])
            data += "; {} l".format(plugin_options['label2'])
            data += "; {} l".format(plugin_options['label3'])
            data += "; {} l".format(plugin_options['label4'])
            data += '\n'

            for interval in log_file:
                data += '; '.join([
                    '{}'.format(interval[0]),
                    '{}'.format(interval[1]),
                    '{}'.format(interval[2]),
                    '{}'.format(interval[3]),
                    '{}'.format(interval[4]),
                    '{}'.format(interval[5]),
                    '{}'.format(interval[6]),
                    '{}'.format(interval[7]),
                    '{}'.format(interval[8]),
                    '{}'.format(interval[9]),
                ]) + '\n'

        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'sql_log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data