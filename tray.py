#!/usr/bin/python
import os
import sys
import time
import datetime
import subprocess

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk as gtk, AppIndicator3 as appindicator, GObject as gobject
from threading import Event, Thread

from protonvpn_cli.utils import (
    is_connected,
    get_config_value,
    get_servers,
    get_server_value,
    get_transferred_data,
)

'''
Set the local paths for the tray icons.
'''
current_path = os.path.dirname(os.path.realpath(__file__))
GREEN_ICON = os.path.join(current_path, 'icons', 'green.png')
RED_ICON = os.path.join(current_path, 'icons', 'red.png')
AMBER_ICON = os.path.join(current_path, 'icons', 'amber.png')

class Indicator():
    def __init__(self):

        self.gtk = gtk
        self.gobject = gobject

        self.trayindicator = appindicator.Indicator.new("protonvpn-tray", RED_ICON, appindicator.IndicatorCategory.APPLICATION_STATUS)
        self.trayindicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.trayindicator.set_menu(self.set_menu())
        self.trayindicator.set_label("", "")

        self.connection_error = True
        self.auth_error = False
        self.network_error = False

        self.main_loop = self.gobject.timeout_add_seconds(1, self.main)
        
        self.main()

        self.gtk.main()

    '''
    Call all the reporters. 
    `True` is returned to allow for scheduling of the next call.
    '''
    def main(self):

        self.report_is_connected()
        self.report_time_connected()
        self.report_location_connected()
        self.report_kill_switch()
        self.report_dns_leak_protection()
        self.report_tray_info()

        return True

    '''
    Define the menu structure. There are three sections:
    - Connection Info
    - Config info
    - Exit
    '''
    def set_menu(self):

        self.menu = self.gtk.Menu()

        self.time_connected = self.gtk.MenuItem(label='')
        self.menu.append(self.time_connected)

        self.location_connected = self.gtk.MenuItem(label='')
        self.menu.append(self.location_connected)
        
        self.separator_1 = self.gtk.SeparatorMenuItem()
        self.menu.append(self.separator_1)
        self.separator_1.show()

        self.quick_connect = self.gtk.MenuItem(label='Quick Connect')
        self.quick_connect.connect('activate', self.try_quick_connect)
        self.menu.append(self.quick_connect)

        self.reconnect = self.gtk.MenuItem(label='')
        self.reconnect.connect('activate', self.try_reconnect)
        self.menu.append(self.reconnect)

        self.disconnect = self.gtk.MenuItem(label='Disconnect')
        self.disconnect.connect('activate', self.try_disconnect)
        self.menu.append(self.disconnect)

        self.separator_2 = self.gtk.SeparatorMenuItem()
        self.menu.append(self.separator_2)
        self.separator_2.show()

        self.kill_switch = self.gtk.MenuItem(label='')
        self.menu.append(self.kill_switch)

        self.dns_leak_protection = self.gtk.MenuItem(label='')
        self.menu.append(self.dns_leak_protection)

        self.separator_3= self.gtk.SeparatorMenuItem()
        self.menu.append(self.separator_3)
        self.separator_3.show()

        self.exittray = self.gtk.MenuItem('Exit')
        self.exittray.connect('activate', self.stop)
        self.menu.append(self.exittray)

        self.menu.show_all()
        return self.menu

    '''
    Verifies if currently connected to a server.
    Sets the colour of the tray indicator icon to reflect the connetion status. 
    '''
    def report_is_connected(self):

        try:
            server = get_config_value("metadata", "connected_server")
            self.reconnect.get_child().set_text("Reconnect to {}".format(server))
        except (KeyError):
            print("Error: No previous connection found. ")

        if is_connected():

            if self.connection_error:
                self.connection_error = False
                self.auth_error = False
                self.network_error = False
                self.trayindicator.set_icon(GREEN_ICON)
        else:

            if not self.connection_error:
                self.connection_error = True
                self.trayindicator.set_icon(RED_ICON)


    '''
    Reports the current time elapsed since the connection was established.
    Sources the epoch time from the ProtonVPI-CLI config via a utility function.
    '''
    def report_time_connected(self):

        connection_time = "-"

        if not self.connection_error:
            try:
                connected_time = get_config_value("metadata", "connected_time")
                connection_time = time.time() - int(connected_time)
                connection_time = str(datetime.timedelta(seconds=(time.time() - int(connected_time)))).split(".")[0]
            except (BaseException):
                print("Error Reporting Time Connected")

        self.time_connected.get_child().set_text("{}".format(connection_time))

    '''
    Reports the location of the currently connected server.
    Sources the connected server from the ProtonVPN-CLI config, and the server info from the 
    local ProtonVPN-CLI server JSON file. 
    '''
    def report_location_connected(self):

        location_string = "-"
        
        if not self.connection_error:
            try:
                servers = get_servers()
                connected_server = get_config_value("metadata", "connected_server")
                country_code = get_server_value(connected_server, "EntryCountry", servers)
                city = get_server_value(connected_server, "City", servers)
                location_string = "{city}, {cc}".format(cc=country_code, city=city)
            except (BaseException):
                print("Error Reporting Connected Server")

        self.location_connected.get_child().set_text(location_string)

    '''
    Reports the Kill Switch status, sourced from the ProtonVPN-CLI config.
    '''
    def report_kill_switch(self):

        kill_switch_status = "-"

        try:
            kill_switch_flag = get_config_value("USER", "killswitch")
            kill_switch_status = "On" if kill_switch_flag == "1" else "Off"
        except (BaseException):
            print("Error Reporting Kill Switch Status")

        self.kill_switch.get_child().set_text("Kill Switch: {}".format(kill_switch_status))

    '''
    Reports the DNS Leak Protection status, sourced from the ProtonVPN-CLI config.
    '''
    def report_dns_leak_protection(self):

        dns_leak_protection_status = "-"

        try:
            dns_leak_protection_flag = get_config_value("USER", "dns_leak_protection")
            dns_leak_protection_status = "On" if dns_leak_protection_flag == "1" else "Off"
        except (BaseException):
            print("Error Reporting DNS Leak Protection Status")

        self.dns_leak_protection.get_child().set_text("DNS Leak Protection: {}".format(dns_leak_protection_status))

    
    '''
    Update the tray label with the current usage statistics.
    If there is an authentication or network error, report this also
    '''
    def report_tray_info(self):

        usage_string = ""

        if "-u" in sys.argv:
            sent_amount, received_amount = get_transferred_data()
            usage_string = "{0} 🠕🠗 {1}".format(sent_amount, received_amount)

        info_char = "🔐   " if self.auth_error else ""
        info_char = "🔗   " if self.network_error else info_char
  
        self.trayindicator.set_label("{0}{1}".format(info_char, usage_string), "")

    
    '''
    Attempts to connect to the fastest VPN server
    '''
    def try_quick_connect(self, _):

        process = subprocess.Popen([self.sudo_type, "protonvpn", "connect", "-f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            response = process.communicate(timeout=30)
            outs = response[0].decode().lower()

            if "there was an error connecting to the protonvpn api" in outs:
                self.network_error = True
                print("Error Whist Attempting Quick Connect: Network Error.")

            if "authentication failed" in outs:
                self.auth_error = True
                print("Error Whist Attempting Quick Connect: Authentication.")

        except subprocess.TimeoutExpired:
            print("Error Whist Attempting Quick Connect: Timeout.")

    '''
    Attempts to reconnect to the last VPN server
    '''
    def try_reconnect(self, _):

        process = subprocess.Popen([self.sudo_type, "protonvpn", "reconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            response = process.communicate(timeout=30)
            outs = response[0].decode().lower()

            if "couldn't find a previous connection" in outs:
                print("Error Whist Attempting Reconnection: No Previous Connection.")
            
            if "there was an error connecting to the protonvpn api" in outs:
                self.network_error = True
                print("Error Whist Attempting Reconnection: Network Error.")

            if "authentication failed" in outs:
                self.auth_error = True
                print("Error Whilst Attempting Reconnection: Authentication.")

        except subprocess.TimeoutExpired:
            print("Error Whilst Attempting Reconnection: Timeout.")

    '''
    Attempts to disconnect from the VPN server
    '''
    def try_disconnect(self, _):

        process = subprocess.Popen([self.sudo_type, "protonvpn", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            print("Error Whist Attempting Disconnect: Timeout.")

    '''
    Returns the user specified sudo type.
    '''
    @property
    def sudo_type(self):

        if "-p" in sys.argv:
            return "pkexec"

        return "sudo"

    '''
    Quits the tray.
    '''
    def stop(self, _):
        self.gobject.source_remove(self.main_loop)
        self.gtk.main_quit()

Indicator()