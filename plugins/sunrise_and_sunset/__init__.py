# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

from threading import Thread, Event, Condition, Lock
import time
import subprocess
import shlex
import sys
import traceback
import json
import os
import shutil

import web
from datetime import datetime
from ospy.webpages import ProtectedPage
from ospy.log import log, logEM, logEV
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.options import options, rain_blocks
from ospy.helpers import datetime_string, verify_csrf
from ospy.programs import programs
from ospy.runonce import run_once
from ospy.inputs import inputs

from ospy.webpages import pluginScripts # Inject javascript to call our API for data and modify the display (in base.html)
from ospy.webpages import showInFooter  # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline

NAME = 'Astro Sunrise and Sunset'
MENU =  _('Package: Astro Sunrise and Sunset')
LINK = 'status_page'
ASTRO_CALC_INTERVAL = 300
MAIN_LOOP_SLEEP = 1
ERROR_BACKOFF = 60
ERROR_LOG_THROTTLE = 60
ASTRAL_APT_PACKAGE = 'python3-astral'

plugin_options = PluginOptions(
    NAME, 
    {
        'use_astro': False,
        'use_script': True,             # enable script injection on homepage
        'location': 0,
        'custom_location': '',
        'custom_region': '',
        'custom_timezone': 'UTC',
        'custom_lati_longit': '',
        'use_footer': False,
        'number_pgm': 2,                # program count number
        'pgm_type': [0, 1],             # 0=sunrise, 1=sunset 
        'time_h': [0, -1],              # move the beginning of the program +- hours
        'time_m': [0, -30],             # move the beginning of the program +- minutes
        'pgm_run': [-1, -1],            # program for running -1 is not selected
        'pgm_enabled': [True, True],              # program for running is enabled
        'ignore_rain': [False, False],            # program for running in rain
        'ignore_rain_delay': [False, False],      # program for running in rain delay
    }
)

if plugin_options['use_script']:
    script_path = "sunrise_and_sunset/script/sunrise_sunset.js"
    if script_path not in pluginScripts:
        pluginScripts.append(script_path)

stats = {}
last_millis = 0
_last_error_log = {'message': None, 'time': 0}
dependency_install_lock = Lock()
dependency_install_running = False
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_calculation': 0,
    'scheduled_programs': 0,
    'last_error': 0,
    'last_error_message': '',
}

city_table = [
    _('Not selected'),
    "Aberdeen",
    "Abu Dhabi",
    "Abuja",
    "Accra",
    "Addis Ababa",
    "Adelaide",
    "Al Jubail",
    "Albany",
    "Albuquerque",
    "Algiers",
    "Amman",
    "Amsterdam",
    "Anchorage",
    "Andorra la Vella",
    "Ankara",
    "Annapolis",
    "Antananarivo",
    "Apia",
    "Ashgabat",
    "Asmara",
    "Astana",
    "Asuncion",
    "Athens",
    "Atlanta",
    "Augusta",
    "Austin",
    "Avarua",
    "Baghdad",
    "Baku",
    "Baltimore",
    "Bamako",
    "Bandar Seri Begawan",
    "Bangkok",
    "Bangui",
    "Banjul",
    "Barrow In Furness",
    "Basse Terre",
    "Basseterre",
    "Baton Rouge",
    "Beijing",
    "Beirut",
    "Belfast",
    "Belgrade",
    "Belmopan",
    "Berlin",
    "Bern",
    "Billings",
    "Birmingham",
    "Birmingham",
    "Bishkek",
    "Bismarck",
    "Bissau",
    "Bloemfontein",
    "Bogota",
    "Boise",
    "Bolton",
    "Boston",
    "Bradford",
    "Brasilia",
    "Bratislava",
    "Brazzaville",
    "Bridgeport",
    "Bridgetown",
    "Brisbane",
    "Bristol",
    "Brussels",
    "Bucharest",
    "Bucuresti",
    "Budapest",
    "Buenos Aires",
    "Buffalo",
    "Bujumbura",
    "Burlington",
    "Cairo",
    "Canberra",
    "Cape Town",
    "Caracas",
    "Cardiff",
    "Carson City",
    "Castries",
    "Cayenne",
    "Charleston",
    "Charlotte",
    "Charlotte Amalie",
    "Cheyenne",
    "Chicago",
    "Chisinau",
    "Cleveland",
    "Columbia",
    "Columbus",
    "Conakry",
    "Concord",
    "Copenhagen",
    "Cotonou",
    "Crawley",
    "Dakar",
    "Dallas",
    "Damascus",
    "Dammam",
    "Denver",
    "Des Moines",
    "Detroit",
    "Dhaka",
    "Dili",
    "Djibouti",
    "Dodoma",
    "Doha",
    "Douglas",
    "Dover",
    "Dublin",
    "Dushanbe",
    "Edinburgh",
    "El Aaiun",
    "Fargo",
    "Fortn de France",
    "Frankfort",
    "Freetown",
    "Funafuti",
    "Gaborone",
    "George Town",
    "Georgetown",
    "Gibraltar",
    "Glasgow",
    "Greenwich",
    "Guatemala",
    "Hanoi",
    "Harare",
    "Harrisburg",
    "Hartford",
    "Havana",
    "Helena",
    "Helsinki",
    "Hobart",
    "Hong Kong",
    "Honiara",
    "Honolulu",
    "Houston",
    "Indianapolis",
    "Islamabad",
    "Jackson",
    "Jacksonville",
    "Jakarta",
    "Jefferson City",
    "Jerusalem",
    "Juba",
    "Jubail",
    "Juneau",
    "Kabul",
    "Kampala",
    "Kansas City",
    "Kathmandu",
    "Khartoum",
    "Kiev",
    "Kigali",
    "Kingston",
    "Kingston",
    "Kingstown",
    "Kinshasa",
    "Koror",
    "Kuala Lumpur",
    "Kuwait",
    "La Paz",
    "Lansing",
    "Las Vegas",
    "Leeds",
    "Leicester",
    "Libreville",
    "Lilongwe",
    "Lima",
    "Lincoln",
    "Lisbon",
    "Little Rock",
    "Liverpool",
    "Ljubljana",
    "Lome",
    "London",
    "Los Angeles",
    "Louisville",
    "Luanda",
    "Lusaka",
    "Luxembourg",
    "Macau",
    "Madinah",
    "Madison",
    "Madrid",
    "Majuro",
    "Makkah",
    "Malabo",
    "Male",
    "Mamoudzou",
    "Managua",
    "Manama",
    "Manchester",
    "Manchester",
    "Manila",
    "Maputo",
    "Maseru",
    "Masqat",
    "Mbabane",
    "Mecca",
    "Medina",
    "Melbourne",
    "Memphis",
    "Mexico",
    "Miami",
    "Milwaukee",
    "Minneapolis",
    "Minsk",
    "Mogadishu",
    "Monaco",
    "Monrovia",
    "Montevideo",
    "Montgomery",
    "Montpelier",
    "Moroni",
    "Moscow",
    "Moskva",
    "Mumbai",
    "Muscat",
    "N'Djamena",
    "Nairobi",
    "Nashville",
    "Nassau",
    "Naypyidaw",
    "New Delhi",
    "New Orleans",
    "New York",
    "Newark",
    "Newcastle",
    "Newcastle Upon Tyne",
    "Ngerulmud",
    "Niamey",
    "Nicosia",
    "Norwich",
    "Nouakchott",
    "Noumea",
    "Nuku'alofa",
    "Nuuk",
    "Oklahoma City",
    "Olympia",
    "Omaha",
    "Oranjestad",
    "Orlando",
    "Oslo",
    "Ottawa",
    "Ouagadougou",
    "Oxford",
    "P'yongyang",
    "Pago Pago",
    "Palikir",
    "Panama",
    "Papeete",
    "Paramaribo",
    "Paris",
    "Perth",
    "Philadelphia",
    "Phnom Penh",
    "Phoenix",
    "Pierre",
    "Plymouth",
    "Podgorica",
    "Port Louis",
    "Port Moresby",
    "Port of Spain",
    "Port Vila",
    "Port au Prince",
    "Portland",
    "Portland",
    "Porto Novo",
    "Portsmouth",
    "Prague",
    "Praia",
    "Pretoria",
    "Pristina",
    "Providence",
    "Quito",
    "Rabat",
    "Raleigh",
    "Reading",
    "Reykjavik",
    "Richmond",
    "Riga",
    "Riyadh",
    "Road Town",
    "Rome",
    "Roseau",
    "Sacramento",
    "Saint Helier",
    "Saint Paul",
    "Saint Pierre",
    "Saipan",
    "Salem",
    "Salt Lake City",
    "San Diego",
    "San Francisco",
    "San Jose",
    "San Juan",
    "San Marino",
    "San Salvador",
    "Sana",
    "Sana'a",
    "Santa Fe",
    "Santiago",
    "Santo Domingo",
    "Sao Tome",
    "Sarajevo",
    "Seattle",
    "Seoul",
    "Sheffield",
    "Singapore",
    "Sioux Falls",
    "Skopje",
    "Sofia",
    "Southampton",
    "Springfield",
    "Sri Jayawardenapura Kotte",
    "St. George's",
    "St. John's",
    "St. Peter Port",
    "Stanley",
    "Stockholm",
    "Sucre",
    "Suva",
    "Swansea",
    "Swindon",
    "Sydney",
    "T'bilisi",
    "Taipei",
    "Tallahassee",
    "Tallinn",
    "Tarawa",
    "Tashkent",
    "Tbilisi",
    "Tegucigalpa",
    "Tehran",
    "Thimphu",
    "Tirana",
    "Tirane",
    "Tokyo",
    "Toledo",
    "Topeka",
    "Torshavn",
    "Trenton",
    "Tripoli",
    "Tunis",
    "Ulaanbaatar",
    "Ulan Bator",
    "Vaduz",
    "Valletta",
    "Vienna",
    "Vientiane",
    "Vilnius",
    "Virginia Beach",
    "W. Indies",
    "Warsaw",
    "Washington DC",
    "Wellington",
    "Wichita",
    "Willemstad",
    "Wilmington",
    "Windhoek",
    "Wolverhampton",
    "Yamoussoukro",
    "Yangon",
    "Yaounde",
    "Yaren",
    "Yerevan",
    "Zagreb",    
    ]
    

class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._done = Condition()
        self._stop_event = runtime.stop_event

        self.status = {}
        self.sunrise = None
        self.sunset = None
        self.mycity = None

        self._sleep_time = 0
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update_wait(self):
        self._done.acquire()
        self._sleep_time = 0
        self._done.wait(4)
        self._done.release()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        global stats, last_millis

        temp_upd = None
        if plugin_options['use_footer']:
            temp_upd = showInFooter() #  instantiate class to enable data in footer
            temp_upd.button = "sunrise_and_sunset/status"    # button redirect on footer
            temp_upd.label =  _('Sunrise and Sunset')        # label on footer
            msg = _('Waiting to state')
            temp_upd.val = msg.encode('utf8').decode('utf8') # value on footer

        try:
            from astral.geocoder import database
        except ImportError:
            log_astral_missing()
            self._sleep(ERROR_BACKOFF)

        millis = 0                                           # timer for computing astro state
        last_millis = 0            
        
        city = None

        run_now_pgm_list = {}
        
        while not self._stop_event.is_set():
            try:
                if plugin_options['use_astro']:
                    millis = int(round(time.time() * 1000))
                    if (millis - last_millis) > (ASTRO_CALC_INTERVAL * 1000):
                        last_millis = millis
                        log.clear(NAME)
                        found_name = ''
                        found_region = ''
                        found_timezone =''
                        found_latitude = 0
                        found_longitude = 0
                        try:
                            if plugin_options['location'] != 0:     # 0 is none location
                                ### find automatic location
                                from astral.geocoder import database, lookup
                                find_loc = city_table[plugin_options['location']]
                                city = lookup(find_loc, database()) # return example: LocationInfo(name='Addis Ababa', region='Ethiopia', timezone='Africa/Addis_Ababa', latitude=9.033333333333333, longitude=38.7)
                                found_name = city.name
                                found_region = city.region
                                found_timezone = city.timezone
                                found_latitude = city.latitude
                                found_longitude = city.longitude
                                self.mycity = city
                            else:
                                if plugin_options['custom_location'] and plugin_options['custom_region'] and plugin_options['custom_timezone'] and plugin_options['custom_lati_longit']:
                                    ### manual location
                                    from astral.geocoder import add_locations, database, lookup
                                    db = database()
                                    _loc = '{},{},{},{}'.format(plugin_options['custom_location'], plugin_options['custom_region'], plugin_options['custom_timezone'], plugin_options['custom_lati_longit'])
                                    add_locations(_loc, db) # "Somewhere,Secret Location,UTC,24°28'N,39°36'E"
                                    city = lookup(plugin_options['custom_location'], db)
                                    found_name = city.name
                                    found_region = city.region
                                    found_timezone = city.timezone
                                    found_latitude = city.latitude
                                    found_longitude = city.longitude
                                    self.mycity = city
                                else:
                                    log.info(NAME, _('You must fill in all required fields (location, region, timezone/name, latitude and longitude!'))
                                    city = None
 
                            if city is not None:
                                log.info(NAME, _('Found city'))
                                log.info(NAME, _('Name') + ': {}'.format(found_name))
                                log.info(NAME, _('Region') + ': {}'.format(found_region))
                                log.info(NAME, _('Timezone') + ': {}'.format(found_timezone))
                                log.info(NAME, _('Latitude') + ': {}'.format(round(found_latitude, 2)))
                                log.info(NAME, _('Longitude') + ': {}'.format(round(found_longitude, 2)))

                                import datetime
                                today =  datetime.date.today()
                                _day = int(today.strftime("%d"))
                                _month = int(today.strftime("%m"))
                                _year = int(today.strftime("%Y"))
                                
                                s = compute_sunrise_sunset()
                                if s is None:
                                    raise ValueError(_('Sunrise and sunset calculation failed.'))
                                self.sunrise = s['sunrise']
                                self.sunset = s['sunset']
                                with health_lock:
                                    health_state['last_calculation'] = time.time()
                                    health_state['last_error_message'] = ''

                                log.info(NAME, '_______________ ' + '{}'.format(today) + ' _______________')
                                log.info(NAME, _('Dawn') + ': {}'.format(s["dawn"].strftime("%H:%M:%S")))
                                log.info(NAME, _('Sunrise') + ': {}'.format(s["sunrise"].strftime("%H:%M:%S")))
                                log.info(NAME, _('Noon') + ': {}'.format(s["noon"].strftime("%H:%M:%S")))
                                log.info(NAME, _('Sunset') + ': {}'.format(s["sunset"].strftime("%H:%M:%S")))
                                log.info(NAME, _('Dusk') + ': {}'.format(s["dusk"].strftime("%H:%M:%S")))

                                msg = _('Sunrise') + ': {}, '.format(s["sunrise"].strftime("%H:%M:%S")) + _('Sunset') + ': {}'.format(s["sunset"].strftime("%H:%M:%S"))

                                ### compute moon phase
                                from astral import moon

                                m = moon.phase(datetime.date(_year, _month, _day))
                                log.info(NAME, _('Moon phase') + ': {}'.format(round(m, 2)))
                                msg += ', ' +  _('Moon phase') + ': '
                                if m < 7:
                                    log.info(NAME, '* ' + _('New moon'))
                                    msg += _('New moon')
                                elif m >= 7  and m < 14:
                                    log.info(NAME, '* ' + _('First quarter'))
                                    msg += _('First quarter')
                                elif m >= 14  and m < 21:
                                    log.info(NAME, '* ' + _('Full moon'))
                                    msg += _('Full moon')
                                elif m >= 21  and m < 28:
                                    log.info(NAME, '* ' + _('Last quarter'))
                                    msg += _('Last quarter')
                                else:
                                    log.info(NAME, '* ' + _('Unkown phase'))
                                    msg += _('Unkown phase')

                        except Exception:
                            self.started.set()
                            city = None
                            run_now_pgm_list = {}
                            log_astro_error(_('Astro plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
                            self._sleep(ERROR_BACKOFF)

                        ### compute starting datetime for selected programs
                        if city is not None:
                            run_now_pgm_list = {}
                            log.info(NAME, '___________ ' + _('Programs for runs') + ' ____________')
                            for i in range(0, plugin_options['number_pgm']):
                                if plugin_options['pgm_type'][int(i)] == 0:  # sunrise
                                    sunrise_time = s["sunrise"]
                                    start_time = sunrise_time + datetime.timedelta(hours=plugin_options['time_h'][int(i)], minutes=plugin_options['time_m'][int(i)])
                                else:                                        # sunset
                                    sunset_time = s["sunset"] 
                                    start_time = sunset_time + datetime.timedelta(hours=plugin_options['time_h'][int(i)], minutes=plugin_options['time_m'][int(i)])
                                if plugin_options['pgm_run'][int(i)] != -1:  # if pgm for run is selected in options
                                    if plugin_options['pgm_enabled'][int(i)]:
                                        if inputs.rain_sensed():    # rain is detected
                                            if plugin_options['ignore_rain'][int(i)]:
                                                run_now_pgm_list[programs[plugin_options['pgm_run'][int(i)]].name] = start_time
                                                log.info(NAME, _('The "{}" will be launched at {} hours (ignore rain).').format(programs[plugin_options['pgm_run'][int(i)]].name, start_time.strftime("%d.%m.%Y %H:%M:%S")))
                                        elif rain_blocks.seconds_left(): # rain delay is activated        
                                            if plugin_options['ignore_rain_delay'][int(i)]:        
                                                run_now_pgm_list[programs[plugin_options['pgm_run'][int(i)]].name] = start_time
                                                log.info(NAME, _('The "{}" will be launched at {} hours (ignore rain delay).').format(programs[plugin_options['pgm_run'][int(i)]].name, start_time.strftime("%d.%m.%Y %H:%M:%S")))
                                        else:
                                            if not inputs.rain_sensed() and not rain_blocks.seconds_left():
                                                run_now_pgm_list[programs[plugin_options['pgm_run'][int(i)]].name] = start_time
                                                log.info(NAME, _('The "{}" will be launched at {} hours.').format(programs[plugin_options['pgm_run'][int(i)]].name, start_time.strftime("%d.%m.%Y %H:%M:%S")))
                                                # example in list {'Program 01': datetime.datetime(2022, 8, 1, 6, 31, 39, 859458, tzinfo=<DstTzInfo 'Europe/Prague' CEST+2:00:00 DST>), 'Program 02': datetime.datetime(2022, 8, 1, 19, 45, 11, 806923, tzinfo=<DstTzInfo 'Europe/Prague' CEST+2:00:00 DST>)}
                            pgmlen = len(run_now_pgm_list)
                            with health_lock:
                                health_state['scheduled_programs'] = pgmlen
                            if pgmlen > 0:
                                msg += ', ' + _('{} programs scheduled').format(pgmlen)                    

                        log.info(NAME, datetime_string() + ' ' + _('Another calculation will take place later.'))

                    ### start run now of the program if the program exists and there is a start time 
                    for pgm_name, start_time in run_now_pgm_list.items():
                        # example from name and time: Program 02 2022-08-01 19:45:11.806923+02:00
                        for pgm_id in programs.get():
                            if pgm_id.name == pgm_name:                                # the program in OSPy has the same name as the program we want to run
                                import pytz
                                tz = pytz.timezone(found_timezone)
                                now = datetime.datetime.now(tz)
                                dist_time = start_time + datetime.timedelta(seconds=1) # we will try to start the program within 1 seconds
                                if now >= start_time and now < dist_time:              # if the set start time from astro is the current time
                                    programs.run_now(pgm_id.index)
                                    log.info(NAME, _('I run the program "{}" in time {}.').format(pgm_name, datetime_string()))

                else:
                    msg =_('Plugin is not enabled')

                
                if plugin_options['use_footer']:
                    if temp_upd is not None:
                        temp_upd.val = msg.encode('utf8').decode('utf8')  # value on footer
                    else:
                        log.error(NAME, _('Error: restart this plugin! Show in homepage footer have enabled.'))

                self._sleep(MAIN_LOOP_SLEEP)

            except Exception:
                self.started.set()
                log_astro_error(_('Astro plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
                self._sleep(ERROR_BACKOFF)

checker = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = StatusChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join(15)
        runtime.join(15)
        if checker.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            checker = None


def health():
    """Return Astral calculation, schedule and worker state."""
    with health_lock:
        state = dict(health_state)
    worker_running = checker is not None and checker.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Astro scheduling enabled'): _('Yes') if plugin_options['use_astro'] else _('No'),
        _('Astral available'): _('Yes') if astral_is_available() else _('No'),
        _('Location'): (
            checker.mycity.name
            if checker is not None and checker.mycity is not None else _('Not available')
        ),
        _('Sunrise'): (
            str(checker.sunrise) if checker is not None and checker.sunrise else _('Not available')
        ),
        _('Sunset'): (
            str(checker.sunset) if checker is not None and checker.sunset else _('Not available')
        ),
        _('Scheduled programs'): state['scheduled_programs'],
        _('Dependency installation running'): (
            _('Yes') if astral_dependencies_installing() else _('No')
        ),
        _('Last successful calculation'): (
            datetime_string(time.localtime(state['last_calculation']))
            if state['last_calculation'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Astro Sunrise and Sunset worker is not running.'),
            'details': details,
        }
    if not plugin_options['use_astro']:
        return {
            'status': 'unknown',
            'summary': _('Astro scheduling is disabled.'),
            'details': details,
        }
    if not astral_is_available():
        return {
            'status': 'error',
            'summary': _('Astral is not installed.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_calculation']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_calculation']:
        return {
            'status': 'unknown',
            'summary': _('Astro Sunrise and Sunset is waiting for its first calculation.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Astro Sunrise and Sunset is responding.'),
        'details': details,
    }

def run_command(cmd):
    try:
        proc = subprocess.run(shlex.split(cmd), stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=120)
        output = proc.stdout.decode('utf-8')
        log.info(NAME, output)

    except Exception:
        log.error(NAME, _('Astral plug-in') + ':\n' + traceback.format_exc())        


def astral_is_available():
    try:
        from astral.geocoder import database
        return True
    except ImportError:
        return False


def log_astral_missing():
    log.clear(NAME)
    log.info(NAME, _('Astral is not installed.'))
    log.info(NAME, _('Install it from the system package manager or from a virtual environment, then restart this plug-in.'))
    log.info(NAME, _('For Raspberry Pi OS try') + ': sudo apt install {}'.format(ASTRAL_APT_PACKAGE))


def astral_dependencies_installing():
    with dependency_install_lock:
        return dependency_install_running


def start_astral_dependency_install():
    global dependency_install_running
    with dependency_install_lock:
        if dependency_install_running:
            log.info(NAME, datetime_string() + ' ' + _('Dependency installation is already running.'))
            return
        dependency_install_running = True

    install_thread = Thread(target=install_astral_dependency)
    install_thread.daemon = True
    install_thread.start()
    runtime.register_thread(install_thread)


def install_astral_dependency():
    global dependency_install_running
    try:
        log.clear(NAME)
        if astral_is_available():
            log.info(NAME, datetime_string() + ' ' + _('Dependencies are already installed.'))
            return

        if os.name != 'posix' or not shutil.which('apt-get'):
            log.error(NAME, datetime_string() + ' ' + _('Automatic dependency installation is available only on systems with apt-get.'))
            log.info(NAME, datetime_string() + ' sudo apt install {}'.format(ASTRAL_APT_PACKAGE))
            return

        cmd = ['apt-get', 'install', '-y', ASTRAL_APT_PACKAGE]
        if hasattr(os, 'geteuid') and os.geteuid() != 0:
            cmd.insert(0, 'sudo')

        log.info(NAME, datetime_string() + ' ' + _('Installing dependencies. This operation can take several minutes.'))
        log.info(NAME, datetime_string() + ' ' + _('Running command') + ': ' + ' '.join(cmd))
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        if process.stdout:
            log.info(NAME, process.stdout)

        if process.returncode == 0 and astral_is_available():
            log.info(NAME, datetime_string() + ' ' + _('Dependencies were installed successfully.'))
            if checker is not None:
                checker.update()
        else:
            log.error(NAME, datetime_string() + ' ' + _('Dependency installation failed. Missing modules') + ': astral')
            log.info(NAME, datetime_string() + ' sudo apt install {}'.format(ASTRAL_APT_PACKAGE))
    except subprocess.TimeoutExpired:
        log.error(NAME, datetime_string() + ' ' + _('Dependency installation timed out.'))
        log.info(NAME, datetime_string() + ' sudo apt install {}'.format(ASTRAL_APT_PACKAGE))
    except Exception:
        log.error(NAME, _('Astral plug-in') + ':\n' + traceback.format_exc())
    finally:
        with dependency_install_lock:
            dependency_install_running = False


def log_astro_error(message):
    now = time.time()
    with health_lock:
        health_state['last_error'] = now
        health_state['last_error_message'] = message
    if message != _last_error_log['message'] or now - _last_error_log['time'] >= ERROR_LOG_THROTTLE:
        _last_error_log['message'] = message
        _last_error_log['time'] = now
        log.error(NAME, message)


def compute_sunrise_sunset(_year = None, _month = None, _day = None):
    from astral.sun import sun
    import datetime
    
    if _year is None and _month is None and _day is None:
        today =  datetime.date.today()
        day = int(today.strftime("%d"))
        month = int(today.strftime("%m"))
        year = int(today.strftime("%Y"))
    else:
        day = int(_day)
        month = int(_month)
        year = int(_year)

    city = checker.mycity
    
    try:
        s = sun(city.observer, date=datetime.date(year, month, day), tzinfo=city.timezone)
        return s
    except:
        return None


def time_to_minutes(time):
    hours, minutes, seconds = map(int, time.split(':'))
    sum_minutes = hours * 60 + minutes
    return sum_minutes


def plugin_data(params):
    # load date param from url to establish date to test
    # ex: params date=2024-08-29
    # not used yet
    s = None

    if hasattr(params,"date"):
        parts = params.date.split("-")
        if len(parts) == 3:  # are there really 3 parts? (year, month, day)
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            s = compute_sunrise_sunset(year, month, day)
        else:
            s = compute_sunrise_sunset()

    if s is not None:
        checker.sunrise = s["sunrise"]
        checker.sunset = s["sunset"]

        # convert to minutes-since-midnight format to return    
        sunrise_minutes = time_to_minutes(checker.sunrise.strftime("%H:%M:%S"))
        sunset_minutes = time_to_minutes(checker.sunset.strftime("%H:%M:%S"))

        if (sunrise_minutes < 0):
            sunrise_minutes += 24*60
        if (sunset_minutes < 0):
            sunset_minutes += 24*60

        return {
            "sunrise" : sunrise_minutes,
            "sunset" : sunset_minutes
        }
    else:
        return {
            "sunrise" : 0,
            "sunset" : 0
        }


################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page astro data."""

    def GET(self):
        global last_millis
        try:
            qdict = web.input()
            install_deps = qdict.get('install_deps') is not None
            if install_deps:
                verify_csrf(qdict)
                start_astral_dependency_install()

            last_millis = 0
            checker.started.wait(4)    # Make sure we are initialized 
            return self.plugin_render.sunrise_and_sunset(
                plugin_options,
                log.events(NAME),
                checker.status,
                city_table,
                not astral_is_available(),
                astral_dependencies_installing()
            )
        except:
            log.error(NAME, _('Astro plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('sunrise_and_sunset -> status_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        global last_millis
        try:
            last_millis = 0
            qdict = web.input()
            verify_csrf(qdict)
            plugin_options.web_update(qdict)
            if checker is not None:
                checker.update()
                checker.update_wait()
            raise web.seeother(plugin_url(status_page), True)
        except:
            log.error(NAME, _('Astro plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('sunrise_and_sunset -> status_page POST')
            return self.core_render.notice('/', msg)


class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        qdict = web.input()
        msg = 'none'
  
        try:
            return self.plugin_render.sunrise_and_sunset_setup(plugin_options, msg)   
        except:
            pgm_type = plugin_options['pgm_type']
            pgm_type.append(int(0))
            plugin_options.__setitem__('pgm_type', pgm_type)

            time_h = plugin_options['time_h']
            time_h.append(int(0))
            plugin_options.__setitem__('time_h', time_h)
            
            time_m = plugin_options['time_m']
            time_m.append(int(0))
            plugin_options.__setitem__('time_m', time_m)

            pgm_run = plugin_options['pgm_run']
            pgm_run.append(int(-1))
            plugin_options.__setitem__('pgm_run', pgm_run)            

            plugin_options.__setitem__('number_pgm', int(1))

            return self.plugin_render.sunrise_and_sunset_setup(plugin_options, msg) 

    def POST(self):
        try:
            global last_millis
            last_millis = 0

            qdict = web.input()
            verify_csrf(qdict)

            if 'number_pgm' in qdict:
                plugin_options.__setitem__('number_pgm', int(qdict['number_pgm']))

            commands = {'pgm_type': [], 'time_h': [], 'time_m': [], 'pgm_run': [], 'pgm_enabled': [], 'ignore_rain': [], 'ignore_rain_delay': []}

            for i in range(0, plugin_options['number_pgm']):
                if 'pgm_type'+str(i) in qdict:
                    commands['pgm_type'].append(int(qdict['pgm_type'+str(i)]))
                else:
                    commands['pgm_type'].append(int(0))

                if 'time_h'+str(i) in qdict:
                    commands['time_h'].append(int(qdict['time_h'+str(i)]))
                else:
                    commands['time_h'].append(int(0))

                if 'time_m'+str(i) in qdict:
                    commands['time_m'].append(int(qdict['time_m'+str(i)]))
                else:
                    commands['time_m'].append(int(0))

                if 'pgm_run'+str(i) in qdict:
                    commands['pgm_run'].append(int(qdict['pgm_run'+str(i)]))
                else:
                    commands['pgm_run'].append(int(-1))

                if 'pgm_enabled'+str(i) in qdict:
                    if qdict['pgm_enabled'+str(i)]=='on':
                        commands['pgm_enabled'].append(True)
                else:
                    commands['pgm_enabled'].append(False)

                if 'ignore_rain'+str(i) in qdict:
                    if qdict['ignore_rain'+str(i)]=='on':                    
                        commands['ignore_rain'].append(True)
                else:
                    commands['ignore_rain'].append(False)

                if 'ignore_rain_delay'+str(i) in qdict:
                    if qdict['ignore_rain_delay'+str(i)]=='on':                    
                        commands['ignore_rain_delay'].append(True)
                else:
                    commands['ignore_rain_delay'].append(False)                                                                          

            plugin_options.__setitem__('pgm_type', commands['pgm_type'])
            plugin_options.__setitem__('time_h', commands['time_h'])
            plugin_options.__setitem__('time_m', commands['time_m'])
            plugin_options.__setitem__('pgm_run', commands['pgm_run'])
            plugin_options.__setitem__('pgm_enabled', commands['pgm_enabled'])
            plugin_options.__setitem__('ignore_rain', commands['ignore_rain'])
            plugin_options.__setitem__('ignore_rain_delay', commands['ignore_rain_delay'])            

            if checker is not None:
                checker.update()

        except Exception:
            log.debug(NAME, _('Astral plug-in') + ':\n' + traceback.format_exc())
            pass

        msg = 'saved'
        return self.plugin_render.sunrise_and_sunset_setup(plugin_options, msg)

class refresh_page(ProtectedPage):
    """Refresh status and show it."""

    def GET(self):
        checker.update_wait()
        raise web.seeother(plugin_url(status_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.sunrise_and_sunset_help()
        except:
            log.error(NAME, _('Sunrise and sunset plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('sunrise_and_sunset -> help_page')
            return self.core_render.notice('/', msg)

class fetch_data(ProtectedPage):
    """Provide fresh data as json to the plugin javascript through an API"""

    def GET(self):
        web.header("Content-Type", "application/json")
        return json.dumps(plugin_data(web.input())) # ex: http://ip:port/plugins/sunrise_and_sunset/fetch_data?date=2024-08-29
