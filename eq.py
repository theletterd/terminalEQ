#!/usr/bin/env python3
import argparse
import curses
from curses import wrapper
import shutil

import numpy as np
import sounddevice as sd

COLUMNS, ROWS = shutil.get_terminal_size()


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser])
parser.add_argument(
    'channels', type=int, default=[1], nargs='*', metavar='CHANNEL',
    help='input channels to plot (default: the first)')
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-r', '--samplerate', type=float, help='sampling rate of audio device')
parser.add_argument(
    '-n', '--downsample', type=int, default=10, metavar='N',
    help='display every Nth sample (default: %(default)s)')
args = parser.parse_args(remaining)
if any(c < 1 for c in args.channels):
    parser.error('argument CHANNEL: must be >= 1')
mapping = [c - 1 for c in args.channels]  # Channel numbers start with 1

stdscr = curses.initscr()
stdscr.nodelay(1)
curses.start_color()
stdscr.clear()

curses.curs_set(0)
curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
curses.init_pair(5, curses.COLOR_BLUE, curses.COLOR_BLACK)
curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
curses.init_pair(8, curses.COLOR_GREEN, curses.COLOR_GREEN)

GREEN = curses.color_pair(1)
YELLOW = curses.color_pair(2)
RED = curses.color_pair(3)
MAGENTA = curses.color_pair(4)
BLUE = curses.color_pair(5)
CYAN = curses.color_pair(6)
WHITE = curses.color_pair(7)
GREEN_BLOCK = curses.color_pair(8)


class Bumper(object):

    def __init__(self, x_displacement, window):
        self.window = window
        self.x_displacement = x_displacement
        self.y_displacement = ROWS - 3
        self.level = 0
        self.max_level = 0

    def get_color_at_level(self, level):
        color = CYAN
        if level >= 3:
            color = GREEN
        if level >= 5:
            color = YELLOW
        if level >= 7:
            color = RED
        return color

    def set_level(self, level):
        self.level = level
        if self.level < 0:
            self.level = 0
        if self.level > 20:
            self.level = 20

        self.max_level -= 0.5

        if self.level >= self.max_level:
            self.max_level = self.level

    def draw(self):
        for i in range(self.level):
            color = self.get_color_at_level(i)

            # draw the bumper itself.
            self.window.addstr(self.y_displacement - i, self.x_displacement, "-", color)
            self.window.addstr(self.y_displacement - i, self.x_displacement + 1 , "-", color)

        # draw max level
        self.window.addstr(self.y_displacement - int(self.max_level) + 1, self.x_displacement, '-', WHITE)
        self.window.addstr(self.y_displacement - int(self.max_level) + 1, self.x_displacement + 1, '-', WHITE)

        # draw numerical value below bumper. Pretty meaningless.
        #self.window.addstr(self.y_displacement + 1, self.x_displacement, str(self.level), WHITE)


class Equalizer(object):

    def __init__(self):
        self.window = curses.newwin(100, 200, 0, 0)
        self.window.nodelay(1)
        self.window.border()

        self.volume_bumper = Bumper(4, self.window)

        self.frequency_bands = ()
        self.freq_bumpers = []
        self.sample_rate = 0


    def set_sample_rate(self, sample_rate):
        # TODO generate bands automatically
        self.sample_rate = sample_rate
        self.frequency_bands = (
            (20, 40),
            (40, 60),
            (60, 80),
            (80, 100),
            (100, 150),
            (150, 200),
            (200, 250),
            (250, 300),
            (300, 350),
            (350, 400),
            (450, 500),
            (500, 600),
            (600, 700),
            (700, 800),
            (800, 900),
            (900, 1000),
            (1000, 1500),
            (1500, 2000),
            (2000, 2500),
            (2500, 3000),
            (3000, 3500),
            (3500, 4000),
            (4000, 4500),
            (4500, 5000),
            (5000, 7000),
            (7000, 10000),
            (10000, 12000),
        )

        # now we need to readjust the bands
        self.freq_bumpers = [Bumper(10 + (i*3), self.window) for i in range(len(self.frequency_bands))]

    def audio_callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        self.window.clear()

        data = indata[:, 0]

        # set volume level.
        level = int(max(data) * 10) + 1
        self.volume_bumper.set_level(level)

        power = np.abs(np.fft.rfft(data, n=frames)) * (2.0 / frames)
        freq = np.fft.rfftfreq(len(data), d=1.0/self.sample_rate)

        halfway = int(len(power) / 2)
        power = power[:halfway]
        freq = freq[:halfway]
        frequency_step = freq[1] - freq[0]

        for bumper_index, (bottom_freq, top_freq) in enumerate(self.frequency_bands):
            bottom_index = int(bottom_freq / frequency_step)
            top_index = int(top_freq / frequency_step)

            try:
                level = max(power[bottom_index:top_index]) *1000
                self.freq_bumpers[bumper_index].set_level(int(level) + 1)
            except:
                self.freq_bumpers[bumper_index].set_level(1)


        bumper_vals = []
        for bumper in self.freq_bumpers:
            bumper_vals.append(bumper.level)
            bumper.draw()

        self.volume_bumper.set_level(int(sum(bumper_vals)/len(bumper_vals)))
        self.volume_bumper.draw()

        self.window.refresh()

def runner(stdscr):
    equalizer = Equalizer()

    try:
        stream = sd.InputStream(
            device=args.device, channels=1,
            samplerate=args.samplerate, callback=equalizer.audio_callback,
            blocksize=int(48000 * 50 / 1000))

        equalizer.set_sample_rate(stream.samplerate)

        with stream:
            sd.sleep(100000000) # something absurdly big so that the program doesn't just shut down
    except Exception as e:
        raise e

wrapper(runner)
