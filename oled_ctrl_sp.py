#!/usr/bin/python
#-*- coding: utf-8 -*-
u'''
http://akizukidenshi.com/catalog/c/coled/
'''

''' for volumio2   Pi2   OLED SO1602AW  3.3V I2C 16x2
sudo apt-get update
sudo apt-get install python-smbus kakasi
'''
import io
import os
import re
import smbus
import socket
import subprocess
import sys
import threading
import time
import traceback


class Oled:
    PANEL_WIDTH = 16

    def __init__(self):
        self.bus = smbus.SMBus(1)
        self.addr = 0x3c          # OLED i2s address
        self.shift = 0            # Scroll shift value
        self.scroll_stop = 0
        self.line1_str = " "      #
        self.line2_str = " "      #
        self.init()

    # initialize OLED
    def init(self):
        retry = 20
        while True:
            try:
                self.bus.write_byte_data(self.addr, 0, 0x0c) # Display ON
                self.line1("Music           ")
                self.line2("  Player Daemon ")
                time.sleep(1)
                ver = subprocess.check_output(['mpd','-V'])
                ver = ver.splitlines()[0]
                ver = re.search(r'\b([\d\.]+)\b', ver).group(1)
                self.line1("MPD Version    ")
                self.line2("        "+ver+"  ")
                time.sleep(2)
                return 0
            except IOError:
                retry -= 1
                if retry == 0:
                    raise
                time.sleep(0.5)

    def _send_line1(self, s):
        slen = len(s)
        if slen < Oled.PANEL_WIDTH:
            s = s + ' ' * (Oled.PANEL_WIDTH - slen)
        elif slen > Oled.PANEL_WIDTH:
            s = s[0:Oled.PANEL_WIDTH]
        #print 'line1: ' + s.decode('cp932') #debug
        vv = map(ord, list(s))
        self.bus.write_byte_data(self.addr, 0, 0x80)
        self.bus.write_i2c_block_data(self.addr, 0x40, vv)

    def _send_line2(self, s):
        slen = len(s)
        if slen < Oled.PANEL_WIDTH:
            s = s + ' ' * (Oled.PANEL_WIDTH - slen)
        elif slen > Oled.PANEL_WIDTH:
            s = s[0:Oled.PANEL_WIDTH]
        #print 'line2: ' + s.decode('cp932') #debug
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
            self.scroll_stop = 4
        else:
            return 0
        try:
            self._send_line2(s)
        except IOError:
            return -1

    def update(self):
        if len(self.line2_str) <= Oled.PANEL_WIDTH:
            return
        if self.scroll_stop > 0:
            self.scroll_stop -= 1
            return
        s = self.line2_str + r'  '
        maxlen = len(s)
        self.shift += 1
        if self.shift >= maxlen:
            self.shift = 0
            self.scroll_stop = 8
        s = s[self.shift:]
        if len(s) < Oled.PANEL_WIDTH:
            s += self.line2_str[0:Oled.PANEL_WIDTH]
        self._send_line2(s)

class MpdCurrentSong:
    __slots__ = ['artist', 'title', 'album', 'name', 'filename']
    def __init__(self, resp):
        for attr in MpdCurrentSong.__slots__:
            setattr(self, attr, r'')
        for line in resp.splitlines():
            if line.startswith(r"Artist: "):
                self.artist = line.replace(r"Artist: ", "")
            elif line.startswith(r"Title: "):
                self.title = line.replace(r"Title: ", "")
            elif line.startswith(r"Album: "):
                self.album = line.replace(r"Album: ", "")
            elif line.startswith(r"Name: "):
                self.name = line.replace(r"Name: ", "")
            elif line.startswith(r"file: "):
                self.filename = line.replace(r"file: ", "")

class MpdStatus:
    __slots__ = ['volume', 'state', 'time', 'bitrate', 'samplerate']
    def __init__(self, resp):
        for attr in MpdStatus.__slots__:
            setattr(self, attr, r'')
        for line in resp.splitlines():
            # Volume
            if line.startswith(r"volume: "):
                self.volume = line.replace("volume: ", "")
            # Play status
            elif line.startswith(r"state: "): # stop play pause
                self.state = line.replace("state: ", "")
            # Plaing time
            elif line.startswith(r"time: "):
                time_val = line.replace("time: ", "")
                time_val = int(time_val.split(':')[0])
                time_min = time_val / 60
                time_sec = time_val % 60
                self.time = '%2d:%02d' % (time_min, time_sec)
            # Bitrate
            elif line.startswith(r"bitrate: "):
                bitr_val = line.replace("bitrate: ", "")
                self.bitrate = bitr_val + 'k'
            # Sampling rate / bit
            elif line.startswith(r"audio: "):
                audio_val = line.replace("audio: ", "")
                audio_val = audio_val.split(':')
                if audio_val[0] == '44100':
                    samp_val = '44.1k'
                elif audio_val[0] == '48000':
                    samp_val = '48k'
                elif audio_val[0] == '88200':
                    samp_val = '88.2k'
                elif audio_val[0] == '96000':
                    samp_val = '96k'
                elif audio_val[0] == '176400':
                    samp_val = '176.4k'
                elif audio_val[0] == '192000':
                    samp_val = '192k'
                elif audio_val[0] == '352800':
                    samp_val = '352.8k'
                elif audio_val[0] == '384000':
                    samp_val = '384k'
                else:
                    samp_val = ''

                bit_val = audio_val[1]+'bit'
                if audio_val[1] == 'dsd':
                    samp_val = self.bitrate
                    bit_val = '1 bit '
                self.samplerate = '%s/%s' % (samp_val, bit_val)

class MpdApi:
    HOST = 'localhost'     # mpd host
    PORT = 6600            # mpd port
    BUFSIZE = 1024

    def __init__(self):
        self.init_socket()

    # Soket Communication
    def init_socket(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.connect((MpdApi.HOST, MpdApi.PORT))
        answer = self.soc.recv(MpdApi.BUFSIZE)
        if not answer.startswith(r'OK MPD'):
            raise RuntimeError('Unexpected Answer: %s' % answer)

    def _request(self, req):
        retry = 5
        while True:
            try:
                self.soc.send(req)
                resp = self.soc.recv(MpdApi.BUFSIZE)
                return resp
            except socket.error:
                retry -= 1
                if retry == 0:
                    raise
                time.sleep(0.5)
                self.init_socket

    # Get current song name
    def get_current_song(self):
        resp = self._request('currentsong\n')
        return MpdCurrentSong(resp)

    def get_status(self):
        resp = self._request('status\n')
        return MpdStatus(resp)

class ShairportSyncWatcher(threading.Thread):
    def __init__(self):
        super(ShairportSyncWatcher, self).__init__()
        self._cmd = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 u'shairport-sync-metadata-reader')
        self._metadata = u'/tmp/shairport-sync-metadata'
        self.state = 'stop'
        self.artist = u''
        self.title = u''
        self.album = u''
        self.duration = 0
        self._prgr_start = 0
        self._prgr_now = 0
        self._prgr_end = 0
        self._prgr_time = time.time()

    def run(self):
        with open(self._metadata) as fh:
            proc = subprocess.Popen([self._cmd], stdin=fh, stdout=subprocess.PIPE)
            for line in iter(proc.stdout.readline, r''):
                self._parse(line)

    def _parse(self, line):
        m = re.match(r'^(.*?): "(.*)".$', line)
        if m:
            if   m.group(1) == r'Artist':
                self.artist = m.group(2)
            elif m.group(1) == r'Title':
                self.title = m.group(2)
            elif m.group(1) == r'Album Name':
                self.album = m.group(2)
            elif m.group(1) == r'"ssnc" "prgr"':
                prgr = m.group(2).split(r'/')
                (start, now, end) = [int(x) / 44100 for x in prgr]
                self.duration = (end - start)
                self._prgr_start = start
                self._prgr_now = now
                self._prgr_end = end
                self._prgr_time = time.time()
                #print 'start: %d, now: %d, end: %d' % (start, now, end)
            elif m.group(1) == r'"ssnc" "pbeg"':
                self.state = 'play'
            elif m.group(1) == r'"ssnc" "pend"':
                self.state = 'stop'
            #else:
            #    print '`%s`: `%s`' % m.group(1,2)

    def get_current_pos(self):
        if self.state != 'stop':
            pos = (self._prgr_now - self._prgr_start) + int(time.time() - self._prgr_time)
            return pos if pos < self.duration else self.duration
        return 0


class Kakasi:
    def __init__(self):
        self._prev_src = None
        self._prev_result = r''

    def toJISx0201kana(self, s):
        if self._prev_src == s:
            return self._prev_result

        proc = subprocess.Popen(['kakasi', '-Jk', '-Hk', '-Kk', '-Ea', '-i', 'utf-8', '-o', 'sjis'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        result = proc.communicate(s)[0]

        self._prev_result = result.rstrip()
        self._prev_src = s
        return self._prev_result


class Controller:
    def __init__(self, oled, mpd_api, shairport_sync_watcher):
        self.oled = oled
        self.mpd_api = mpd_api
        self.shairport_sync_watcher = shairport_sync_watcher
        self.old_vol = " "        # old volume
        self.vol_disp = 0
        self.kakasi = Kakasi()

    # get IP address
    def _get_ip_addr(self):
        ip = subprocess.check_output(['ip', 'route'])
        ip_list = ip.splitlines()
        match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', ip_list[1])
        addr = match.group(1) if match else ''
        return addr

    def _disp_mpd(self):
        status = self.mpd_api.get_status()

        # Volume string
        if self.old_vol != status.volume:
            self.old_vol = status.volume
            self.vol_disp = 5
        else:
            if self.vol_disp > 0:
                self.vol_disp -= 1

        # Volume and status for Line1
        if status.state == 'stop':
            if self.vol_disp > 0:
                self.oled.line1("STOP     Vol:" + status.volume)
            else:
                self.oled.line1("STOP             ")
            self.oled.line2(self._get_ip_addr())
        elif status.state == 'play':
            if self.vol_disp > 0:
                self.oled.line1("PLAY     Vol:" + status.volume)
            else:
                self.oled.line1("PLAY      " + status.time)
        elif status.state == 'pause':
            if self.vol_disp > 0:
                self.oled.line1("PAUSE    Vol:" + status.volume)
            else:
                self.oled.line1("PAUSE     " + status.time)

        # music name for Line2
        if status.state != 'stop':
            song = self.mpd_api.get_current_song()
            if not (song.title or song.name or song.artist):
                song_txt = song.filename
            else:
                artist_or_album_or_name = [song.artist, song.album, song.name]
                artist_or_album_or_name = ' - '.join([x for x in artist_or_album_or_name if x])
                song_txt = '{0:s} : {1:s}'.format(song.title, artist_or_album_or_name)
            song_txt = self.kakasi.toJISx0201kana(song_txt)
            song_txt = r'{0:s} - {1:s} {2:s}bps'.format(song_txt, status.samplerate, status.bitrate)
            self.oled.line2(song_txt)

    def _disp_shairport_sync(self):
        watcher = self.shairport_sync_watcher

        time = '%2d:%02d' % (watcher.get_current_pos() / 60, watcher.get_current_pos() % 60)
        self.oled.line1('{0:8s}  {1:6s}'.format(watcher.state.upper(), time))

        song = '{title:s} : {artist:s} - {album:s}  '.format(artist=watcher.artist, title=watcher.title, album=watcher.album)
        song = self.kakasi.toJISx0201kana(song)
        self.oled.line2(song)

    # Display Control
    def disp(self):
        if self.shairport_sync_watcher.state != 'stop':
            self._disp_shairport_sync()
        else:
            self._disp_mpd()

    def start(self):
        while True:
            try:
                self.disp()
                time.sleep(0.25)
                self.oled.update()
            except Exception as e:
                traceback.print_exc()
                self.oled.line1(type(e).__name__)
                self.oled.line2(str(e))
                time.sleep(10)


def main():
    while True:
        ip = subprocess.check_output(['ip', 'route'])
        ip_list = ip.splitlines()
        if len(ip_list) >= 1:
            break
        time.sleep(1)

    oled = Oled()
    mpd_api = MpdApi()
    shairport_sync_watcher = ShairportSyncWatcher()
    shairport_sync_watcher.start()
    controller = Controller(oled, mpd_api, shairport_sync_watcher)
    controller.start()

if __name__ == '__main__':
    main()
    #state = VolumioState()
    #for attr in state.__slots__:
    #    v = getattr(state, attr)
    #    v = v.encode('utf-8') if isinstance(v, unicode) else v
    #    print attr, ': ', v
