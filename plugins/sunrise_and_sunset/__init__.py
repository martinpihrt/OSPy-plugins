# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

from threading import Thread, Event, Condition
import time
import subprocess
import sys
import traceback

import web
from ospy.webpages import ProtectedPage
from ospy.log import log, logEM, logEV
from plugins import PluginOptions, plugin_url
from ospy.options import options
from ospy.helpers import datetime_string

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline


NAME = 'Astro Sunrise and Sunset'
MENU =  _(u'Package: Astro Sunrise and Sunset')
LINK = 'status_page'

plugin_options = PluginOptions(
    NAME, 
    {
        'use_astro': False,
        'location': 0,
        'custom_location': '',
        'custom_region': '',
        'custom_timezone': 'UTC',
        'custom_lati_longit': '',
        'use_footer': False,
    }
)

stats = {
    'can_update': False,
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
        self._stop_event = Event()

        self.status = {
            'can_update': False
            }

        self._sleep_time = 0
        self.start()

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
        global stats

        temp_upd = None
        if plugin_options['use_footer']:
            temp_upd = showInFooter() #  instantiate class to enable data in footer
            temp_upd.button = "sunrise_and_sunset/status"    # button redirect on footer
            temp_upd.label =  _(u'Sunrise and Sunset')       # label on footer
            msg = _(u'Waiting to state')
            temp_upd.val = msg.encode('utf8').decode('utf8') # value on footer

        try:
            from astral.geocoder import database
        except ImportError:
            log.clear(NAME)
            log.info(NAME, _('Astral is not installed.'))
            log.info(NAME, _('Please wait installing astral...'))
            cmd = "pip3 install astral"
            run_command(cmd)
            log.info(NAME, _('Astral is now installed.'))        

        while not self._stop_event.is_set():
            try:
                if plugin_options['use_astro']:
                    log.clear(NAME)
                    city = None
                    found_name = ''
                    found_region = ''
                    found_timezone =''
                    found_latitude = 0
                    found_longitude = 0
                    try:
                        if plugin_options['location'] != 0:     # 0 is none location
                            from astral.geocoder import database, lookup
                            find_loc = city_table[plugin_options['location']]
                            city = lookup(find_loc, database()) # return example: LocationInfo(name='Addis Ababa', region='Ethiopia', timezone='Africa/Addis_Ababa', latitude=9.033333333333333, longitude=38.7)
                            found_name = city.name
                            found_region = city.region
                            found_timezone = city.timezone
                            found_latitude = city.latitude
                            found_longitude = city.longitude
                        else:
                            if plugin_options['custom_location'] and plugin_options['custom_region'] and plugin_options['custom_timezone'] and plugin_options['custom_lati_longit']:
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
                            else:
                                log.info(NAME, _('You must fill in all required fields (location, region, timezone/name, latitude and longitude!'))
                                city = None

                        s = None 
                        if city is not None:
                            log.info(NAME, _('Found city'))
                            log.info(NAME, _('Name') + ': {}'.format(found_name))
                            log.info(NAME, _('Region') + ': {}'.format(found_region))
                            log.info(NAME, _('Timezone') + ': {}'.format(found_timezone))
                            log.info(NAME, _('Latitude') + ': {}'.format(round(found_latitude, 2)))
                            log.info(NAME, _('Longitude') + ': {}'.format(round(found_longitude, 2)))

                            import datetime
                            from astral.sun import sun

                            today =  datetime.date.today()

                            _day = int(today.strftime("%d"))
                            _month = int(today.strftime("%m"))
                            _year = int(today.strftime("%Y"))

                            s = sun(city.observer, date=datetime.date(_year, _month, _day))
                            log.info(NAME, '________________________________________')
                            log.info(NAME, _('Dawn') + ': {}'.format(s["dawn"]))
                            log.info(NAME, _('Sunrise') + ': {}'.format(s["sunrise"]))
                            log.info(NAME, _('Noon') + ': {}'.format(s["noon"]))
                            log.info(NAME, _('Sunset') + ': {}'.format(s["sunset"]))
                            log.info(NAME, _('Dusk') + ': {}'.format(s["dusk"]))

                            msg = _('Sunrise') + ': {}, '.format(s["sunrise"]) + _('Sunset') + ': {}'.format(s["sunset"])

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
                        log.error(NAME, _('Astro plug-in') + ':\n' + traceback.format_exc())
                        self._sleep(2)
                else:
                    msg =_(u'Plugin is not enabled')

                if plugin_options['use_footer']:
                    if temp_upd is not None:
                        temp_upd.val = msg.encode('utf8').decode('utf8')  # value on footer
                    else:
                        log.error(NAME, _(u'Error: restart this plugin! Show in homepage footer have enabled.'))

                self._sleep(3600)

            except Exception:
                self.started.set()
                log.error(NAME, _('Astro plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

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
        checker.join()
        checker = None

def run_command(cmd):
    try:
        proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT, # merge stdout and stderr
        stdout=subprocess.PIPE,
        shell=True)
        output = proc.communicate()[0].decode('utf-8')
        log.info(NAME, output)

    except Exception:
        log.error(NAME, _(u'Astral plug-in') + ':\n' + traceback.format_exc())        


################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page astro data."""

    def GET(self):
        checker.started.wait(4)    # Make sure we are initialized
        return self.plugin_render.sunrise_and_sunset(plugin_options, log.events(NAME), checker.status, city_table)

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
            checker.update_wait()

        raise web.seeother(plugin_url(status_page), True)


class refresh_page(ProtectedPage):
    """Refresh status and show it."""

    def GET(self):
        checker.update_wait()
        raise web.seeother(plugin_url(status_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.sunrise_and_sunset_help()