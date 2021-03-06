#!/usr/bin/python
# Copyright 2015 Telefonica Investigacion y Desarrollo, S.A.U
#
# This file is part of FlaskContextProvider.
#
# FlaskContextProvider is free software: you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# FlaskContextProvider is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Orion Context Broker. If not, see http://www.gnu.org/licenses/.


import xml.etree.ElementTree as ET
import tools.DataManager as DM
from xml.dom import minidom
import unicodedata
import requests
import urllib2
import inspect
import json
import time
import re
import os


def norm_data(s):
    """
    Normalizes data
        :param s: string to normalize
        :rtype : str
    """
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))


def norm_time(s):
    """
    Parses time value to ISO8601 format
        :param s: time in seconds since the epoch
        :rtype : str
    """
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.localtime(float(s)))


def get_stations():
    """
    Obtains the stations xml provided by http://www.sevici.es
        :rtype : list
    """
    try:
        response = urllib2.urlopen('http://www.sevici.es/service/carto')
        xmldoc = minidom.parse(response)
        item_list = xmldoc.getElementsByTagName('marker')
        stations = []

        for s in item_list:
            station_dict = {
                'number': norm_data(s.attributes['number'].value),
                'name': norm_data(s.attributes['name'].value),
                'address': norm_data(s.attributes['address'].value),
                'fulladdress': norm_data(s.attributes['fullAddress'].value),
                'latitude': norm_data(s.attributes['lat'].value),
                'longitude': norm_data(s.attributes['lng'].value),
                'open': norm_data(s.attributes['open'].value),
                'bonus': norm_data(s.attributes['bonus'].value)
            }
            stations.append(station_dict)

        return stations
    except ValueError:
        return 0


def make_stations_jsonfile():
    """
    Creates a new stations json file
    """
    stations = get_stations()
    if stations != 0:
        sevici_path = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
        if not os.path.exists('%s/file' % sevici_path):
            os.mkdir('%s/file' % sevici_path)
        with open('%s/file/stations.json' % sevici_path, 'w') as jsonfile:
            jstations = json.dumps(stations)
            jsonfile.write(jstations)


def load_stations():
    """
    Loads the stations list
        :rtype : list
    """
    try:
        sevici_path = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
        with open('%s/file/stations.json' % sevici_path, 'r') as stations_file:
            stations = json.loads(stations_file.read())
        return stations
    except Exception:
        return 0


def select_id(orion_id):
    """
    Select the sevici id
        :param orion_id: orion_id
        :rtype : sevici_id
    """
    pattern = "Sevici."
    a = len(re.match(pattern, orion_id).group())
    return orion_id[a:]


def get_station_data(sevici_id):
    """
    Makes the sevici request
        :param sevici_id: sevici id number
        :rtype : list
    """
    url = 'http://www.sevici.es/service/stationdetails/seville/'+sevici_id
    response = requests.get(url)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    fields = root.findall("*")

    return fields


def get_data(_id, _type, max_time=1):
    """
    Parses the response in xml format
        :param _id: entity id
        :rtype : list
    """
    entity = DM.Entity()
    id_ = select_id(_id)

    life_time = []
    try:
        fields = get_station_data(id_)
        entity.entity_add(_id, 'bikerenting', ispattern='false')

        for s in fields:
            if s.tag == "updated":
                s.tag = "timeinstant"
                life_time.append(float(s.text))
                s.text = norm_time(s.text)
                fieldtype = "urn:x-ogc:def:trs:IDAS:1.0:ISO8601"
            else:
                fieldtype = "integer"

            entity.attribute.attribute_add(s.tag, fieldtype, s.text)

        stations = load_stations()
        if stations == 0:
            make_stations_jsonfile()
            stations = load_stations()

        if stations != 0:
            for station in stations:
                if station['number'] == str(id_):
                    pos = station['latitude']+","+station['longitude']
                    entity.attribute.attribute_add('position', 'coords', pos)
                    entity.attribute.metadata.metadata_add('location', 'string', 'WGS84')
                    entity.attribute.add_metadatas_to_attrib('position')
                    entity.attribute.metadata.metadata_list_purge()
                    street = str(station['fulladdress']).title().replace('/','').replace('(','').replace(')','').replace("'","").replace("-","")
                    entity.attribute.attribute_add('street', 'string', street)

        entity.add_attributes_to_entity(_id)
        entity.attribute.attribute_list_purge()

        response_data = entity.get_entity_list()[:]
        entity.entity_list_purge()
        l_time = (time.time() - max(life_time))

        if l_time < 1:
            l_time = 1
        else:
            l_time = max_time - l_time

        return [response_data, l_time]

    except:
        return [[], 1]