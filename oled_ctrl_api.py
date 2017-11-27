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
import commands
import smbus
import sys
import re
import io
import json
import pycurl

class VolumioState:
    __slots__ = ['status', 'album', 'title', 'artist', 'seek', 'samplerate', 'bitdepth', 'volume']

    def __init__(self):
        curl = pycurl.Curl()
        curl.setopt(pycurl.URL, 'http://localhost:3000/api/v1/getstate')
        sio = io.StringIO()
        def writer(str):
            sio.write(str.decode('utf-8'))
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

class i2c(object):
    def __init__(self):
        self.bus = smbus.SMBus(1)
        self.addr = 0x3c          # OLED i2s address
        self.state = STOP         # state
        self.shift = 0            # Scroll shift value
        self.retry = 20           # retry for initialize
        self.old_line1 = " "      # old str 1
        self.old_line2 = " "      # old str 2
        self.old_vol = " "        # old volume
        self.init()

    # initialize OLED
    def init(self):
        while self.retry > 0:
            try:
                self.bus.write_byte_data(self.addr, 0, 0x0c) # Display ON
                self.line1("Music           ")
                self.line2("  Player Daemon ",0)
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
        self.line2("        "+ver+"  ",0)

    # line1 send ascii data
    def line1(self, str):
        if str != self.old_line1:
            self.old_line1 = str
        else:
            return 0
        try:
            print str #debug
            self.bus.write_byte_data(self.addr, 0, 0x80)
            vv = map(ord, list(str))
            self.bus.write_i2c_block_data(self.addr, 0x40, vv)
        except IOError:
            return -1

    # line2 send ascii data and Scroll
    def line2(self, str, sp):
        try:
            self.bus.write_byte_data(self.addr, 0, 0xA0)
            self.maxlen = len(str) +MSTOP
            if sp < MSTOP:
                sp = 0
            else:
                sp = sp -MSTOP -1
            if self.maxlen > sp + 16:
                self.maxlen = sp + 16

            moji = str[sp:self.maxlen]
            print moji.decode('cp932').encode('utf-8') #debug
            moji = map(ord, moji)
            self.bus.write_i2c_block_data(self.addr, 0x40, moji)
        except IOError:
            return -1

    # Get current song name
    def song(self, state):
        if state.artist:
            song_val = '%s : %s' % (state.artist, state.title)
        else:
            song_val = state.title

        song_val = re.escape(song_val)
        song_val = commands.getoutput('echo ' + song_val.encode('utf-8') +' | kakasi -Jk -Hk -Kk -Ea -s -i utf-8 -o sjis')

        #print song_val.decode('cp932').encode('utf-8') #debug
        return song_val

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

        # stop
        if state.status == 'stop':
            # get IP address
            ad = commands.getoutput('ip route')
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
                self.line1("STOP     Vol:"+vol_val)
            else:
                self.line1("STOP             ")
                self.line2(addr_str+"        ",0)
                self.old_line2 = " "
        elif state_val == 'play':
            if self.vol_disp != 0:
                self.line1("PLAY     Vol:"+vol_val)
            else:
                self.line1("PLAY      "+time_val+"  ")
        elif state_val == 'pause':
            if self.vol_disp != 0:
                self.line1("PAUSE    Vol:"+vol_val)
            else:
                self.line1("PAUSE     "+time_val+"  ")

        # music name for Line2
        if state_val != 'stop':
            song_txt = self.song(state)
            song_txt = r'%s - %s/%s ' % (song_txt, samp_val.encode('cp932'), bitr_val.encode('cp932'))

            if song_txt != self.old_line2:
                print 'song change', song_txt.decode('cp932').encode('utf-8') #debug
                self.old_line2 = song_txt
                self.shift = 0
                self.line2("                ", 0)
            self.line2(self.old_line2, self.shift)

        self.shift = self.shift + 1
        if self.shift > (len(self.old_line2)+8 +MSTOP):
            self.shift = 0


def main():
    oled = i2c()
    netlink = False
    time.sleep(1)
    ver = commands.getoutput('mpd -V')
    ver_list = ver.splitlines()
    oled.ver_disp(ver_list[0])
    time.sleep(2)

    while netlink is False:
        ip = commands.getoutput('ip route')
        ip_list = ip.splitlines()
        if len(ip_list) >= 1:
            netlink = True
        else:
            time.sleep(1)

    while True:
        time.sleep(0.25)
        try:
            oled.disp()
        except:
            time.sleep(1)
        pass

if __name__ == '__main__':
    main()
    #state = VolumioState()
    #for attr in state.__slots__:
    #    v = getattr(state, attr)
    #    v = v.encode('utf-8') if isinstance(v, unicode) else v
    #    print attr, ': ', v
