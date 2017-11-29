#!/usr/bin/python
#-*- coding: utf-8 -*-
u'''
http://akizukidenshi.com/catalog/c/coled/
'''

''' for volumio2   Pi2   OLED SO1602AW  3.3V I2C 16x2
sudo apt-get update
sudo apt-get install python-smbus kakasi
'''
import time
import smbus
import sys
import re
import io
import json
import pycurl
from subprocess import check_output, Popen, PIPE

class VolumioState:
    __slots__ = ['status', 'album', 'title', 'artist', 'seek', 'samplerate', 'bitdepth', 'volume']

    def __init__(self):
        curl = pycurl.Curl()
        curl.setopt(pycurl.URL, 'http://localhost:3000/api/v1/getstate')
        sio = io.StringIO()
        def writer(s):
            sio.write(s.decode('utf-8'))
        curl.setopt(pycurl.WRITEFUNCTION, writer)
        curl.perform()
        #print sio.getvalue().encode('utf-8') #debug
        data = json.loads(sio.getvalue())
        for attr in self.__slots__:
            if attr in data:
                setattr(self, attr, data[attr])
            else:
                setattr(self, attr, None)

STOP = 0
PLAY = 1
PAUSE = 2
MSTOP = 1    # Scroll motion stop time

class Display:
    PANEL_WIDTH = 16

    def __init__(self):
        self.bus = smbus.SMBus(1)
        self.addr = 0x3c          # OLED i2s address
        self.state = STOP         # state
        self.shift = 0            # Scroll shift value
        self.retry = 20           # retry for initialize
        self.line1_str = " "      #
        self.line2_str = " "      #
        self.init()

    # initialize OLED
    def init(self):
        while self.retry > 0:
            try:
                self.bus.write_byte_data(self.addr, 0, 0x0c) # Display ON
                self.line1("Music           ")
                self.line2("  Player Daemon ")
            except IOError:
                self.retry = self.retry -1
                time.sleep(0.5)
            else:
                return 0
        else:
            sys.exit()

    # mpd version
    def ver_disp(self, ver):
        ver = ver.replace(r"Music Player Daemon ", "")
        self.line1("MPD Version    ")
        self.line2("        "+ver+"  ")

    def _send_line1(self, s):
        s = s[0:self.PANEL_WIDTH]
        print 'line1: ' + s.decode('cp932') #debug
        vv = map(ord, list(s))
        self.bus.write_byte_data(self.addr, 0, 0x80)
        self.bus.write_i2c_block_data(self.addr, 0x40, vv)

    def _send_line2(self, s):
        s = s[0:self.PANEL_WIDTH]
        print 'line2: ' + s.decode('cp932') #debug
        vv = map(ord, list(s))
        self.bus.write_byte_data(self.addr, 0, 0xA0)
        self.bus.write_i2c_block_data(self.addr, 0x40, vv)

    # line1 send ascii data
    def line1(self, s):
        if s != self.line1_str:
            self.line1_str = s
        else:
            return 0
        try:
            self._send_line1(s)
        except IOError:
            return -1

    # line2 send ascii data
    def line2(self, s):
        if s != self.line2_str:
            self.line2_str = s
            self.shift = 0
        else:
            return 0
        try:
            self._send_line2(s)
        except IOError:
            return -1

    def scroll_line2(self):
        if len(self.line2_str) <= self.PANEL_WIDTH:
            return
        s = self.line2_str + r'  '
        maxlen = len(s)
        self.shift += 1
        if self.shift >= maxlen:
            self.shift = 0
        s = s[self.shift:]
        if len(s) < self.PANEL_WIDTH:
            s += self.line2_str[0:self.PANEL_WIDTH]
        self._send_line2(s)

class Controller:
    def __init__(self, display):
        self.display = display
        self.old_vol = " "        # old volume

    # Get current song name
    def song(self, state):
        if state.artist:
            song_val = '%s : %s' % (state.artist, state.title)
        else:
            song_val = state.title
        return song_val

    def toJISx0201kana(self, s):
        proc = Popen('kakasi -Jk -Hk -Kk -Ea -i utf-8 -o sjis'.split(), stdin=PIPE, stdout=PIPE)
        stdout_data = proc.communicate(s.encode('utf-8'))[0]
        return stdout_data.rstrip()

    # Display Control
    def disp(self):
        state = VolumioState()

        bitr_val = audio_val = time_val = vol_val = state_val = samp_val = bit_val = ""

        vol_val = "%2d" % state.volume
        vol_val = str(vol_val)+' '

        state_val = state.status

        time_val = state.seek % 1000
        time_min = time_val / 60
        time_sec = time_val % 60
        time_min = "%2d" % time_min
        time_sec = "%02d" % time_sec
        time_val = str(time_min)+":"+str(time_sec)

        bitr_val = state.bitdepth
        samp_val = state.samplerate
        samp_val = '%.1f KHz' % samp_val if isinstance(samp_val, float) else str(samp_val)

        # stop
        if state.status == 'stop':
            # get IP address
            ad = check_output('ip route'.split())
            ad_list = ad.splitlines()
            addr_line = re.search('(\d+\.\d+\.\d+\.\d+) .*$', ad_list[1])
            addr_str = addr_line.group(1)

        # Volume string
        if self.old_vol != vol_val:
            self.old_vol = vol_val
            self.vol_disp = 5
        else:
            if self.vol_disp != 0:
                self.vol_disp = self.vol_disp -1

        # Volume and status for Line1
        if state_val == 'stop':
            if self.vol_disp != 0:
                self.display.line1("STOP     Vol:"+vol_val)
            else:
                self.display.line1("STOP             ")
                self.display.line2(addr_str)
        elif state_val == 'play':
            if self.vol_disp != 0:
                self.display.line1("PLAY     Vol:"+vol_val)
            else:
                self.display.line1("PLAY      "+time_val+"  ")
        elif state_val == 'pause':
            if self.vol_disp != 0:
                self.display.line1("PAUSE    Vol:"+vol_val)
            else:
                self.display.line1("PAUSE     "+time_val+"  ")

        # music name for Line2
        if state_val != 'stop':
            song_txt = self.song(state)
            song_txt = self.toJISx0201kana(song_txt)
            song_txt = r'%s - %s/%s ' % (song_txt, samp_val.encode('cp932'), bitr_val.encode('cp932'))
            self.display.line2(song_txt)

        self.display.scroll_line2()

def main():
    display = Display()
    controller = Controller(display)
    netlink = False
    time.sleep(1)
    ver = check_output('mpd -V'.split())
    ver_list = ver.splitlines()
    display.ver_disp(ver_list[0])
    time.sleep(2)

    while netlink is False:
        ip = check_output('ip route'.split())
        ip_list = ip.splitlines()
        if len(ip_list) >= 1:
            netlink = True
        else:
            time.sleep(1)

    while True:
        time.sleep(0.25)
        try:
            controller.disp()
        except:
            import traceback
            traceback.print_exc()
            time.sleep(1)

if __name__ == '__main__':
    main()
    #state = VolumioState()
    #for attr in state.__slots__:
    #    v = getattr(state, attr)
    #    v = v.encode('utf-8') if isinstance(v, unicode) else v
    #    print attr, ': ', v
