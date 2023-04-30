from collections import namedtuple, deque
import pprint
import time
from typing import Optional

from serial_morse_listener.utils import StreamingStats

SYMBOL_DIT = '.'
SYMBOL_DAH = '-'
SYMBOL_INTRA_CHAR_SPACE = ''
SYMBOL_INTER_CHAR_SPACE = ''
SYMBOL_INTER_WORD_SPACE = ' '
DEFAULT_LONG_DURATION = 1000
KEYS_SYMBOLS = ['dit', 'dah', 'intrachar_space', 'interchar_space', 'interword_space']
INTER_CHAR_SPACE_LB = 2.5
INTER_WORD_SPACE_LB = 6
DAH_LB = 1.5


class MorseStreamProcessor:
    Event = namedtuple('event', ['state', 'time'])

    def __init__(self, wpm: float):
        self.wpm = wpm
        self.timing_unit = self.calculate_dit_duration(wpm=wpm)
        self.symbol_buffer = ''
        self.first_event = False
        self.zero_count = 0
        self.last_event = self.Event(-1, -1.0)
        self.history_buffer = deque(maxlen=int(1E6))

        self.stats = {k: StreamingStats() for k in KEYS_SYMBOLS}

        self.character_table = {
            SYMBOL_INTER_WORD_SPACE: ' ',
            '.-': 'a',
            '-...': 'b',
            '-.-.': 'c',
            '-..': 'd',
            '.': 'e',
            '..-.': 'f',
            '--.': 'g',
            '....': 'h',
            '..': 'i',
            '-.-': 'k',
            '.-..': 'l',
            '--': 'm',
            '-.': 'n',
            '---': 'o',
            '.--.': 'p',
            '--.-': 'q',
            '.-.': 'r',
            '...': 's',
            '-': 't',
            '..-': 'u',
            '...-': 'v',
            '.--': 'w',
            '-..-': 'x',
            '-.--': 'y',
            '--..': 'z',
            '.----': '1',
            '..---': '2',
            '...--': '3',
            '....-': '4',
            '.....': '5',
            '-....': '6',
            '--...': '7',
            '---..': '8',
            '----.': '9',
            '-----': '0',
            '...---...': '<SOS>'
        }

    @staticmethod
    def calculate_dit_duration(wpm: float) -> float:
        """
        Calculate dit duration based on a words-per-minute speed. The standard for Morse Code is apparently based on
        the word "Paris", which sums to a convenient 50 dits of time (considering dits, dahs, intra-character spaces,
        inter-character spaces, and a word space).
        See https://morsecode.world/international/timing.html for more details
        :param wpm: words-per-minute
        :return: Dit duration in seconds, as a float
        """
        return (60.0/50.0)*(1.0/wpm)

    def interpret_buffer(self) -> Optional[str]:
        to_interpret = self.symbol_buffer
        self.symbol_buffer = ''
        if to_interpret == SYMBOL_INTER_CHAR_SPACE:
            # This can happen due to timing of when interpret is called
            interpreted = None
        else:
            debug_print = f'?<{to_interpret}>'
            interpreted = self.character_table.get(to_interpret, debug_print)
        return interpreted

    def process_event(self, state: int) -> Optional[str]:
        self.history_buffer.append(state)
        event_time = time.time()
        self.first_event = self.first_event | (state == 1)
        output_char = f'{state}'

        if self.first_event:
            if self.last_event.state == -1:
                last_duration = DEFAULT_LONG_DURATION  # assume long time
            else:
                last_duration = (event_time - self.last_event.time) / self.timing_unit

            if state == 1:
                if self.last_event.state == 0:
                    # We just ended some kind of space
                    self.last_event = self.Event(1, event_time)
                    if last_duration < INTER_CHAR_SPACE_LB:
                        # This was an intra-character space.
                        # No output yet
                        self.symbol_buffer += SYMBOL_INTRA_CHAR_SPACE
                        self.stats['intrachar_space'].update(last_duration)
                        output_char = None
                    elif last_duration < INTER_WORD_SPACE_LB:
                        # This was an inter-character space.
                        # we may have already caught this, so the buffer may be empty
                        self.symbol_buffer += SYMBOL_INTER_CHAR_SPACE
                        self.stats['interchar_space'].update(last_duration)
                        output_char = self.interpret_buffer()
                    else:
                        # Inter-word space. We may have already caught this, maybe not.
                        self.symbol_buffer += SYMBOL_INTER_WORD_SPACE
                        if last_duration < DEFAULT_LONG_DURATION:
                            # Only collect stats on the truly measured times
                            self.stats['interword_space'].update(last_duration)
                        output_char = self.interpret_buffer()
                elif self.last_event.state == 1:
                    # Keep waiting to see the length of the on-state
                    output_char = None
                elif self.last_event.state == -1:
                    # We are waking up
                    self.last_event = self.Event(1, event_time)
                    output_char = None
            elif state == 0:
                if self.last_event.state == 0:
                    if last_duration >= INTER_WORD_SPACE_LB:
                        # Consider this an inter-word space
                        self.symbol_buffer += SYMBOL_INTER_WORD_SPACE
                        output_char = self.interpret_buffer()
                        self.last_event = self.Event(-1, -1.0)
                    elif last_duration >= INTER_CHAR_SPACE_LB:
                        # Consider this at least an inter-character space
                        self.symbol_buffer += SYMBOL_INTER_CHAR_SPACE
                        output_char = self.interpret_buffer()
                        # We'll still wait to see if this ends up being an inter-word space
                    else:
                        # Wait to see the duration of the space.
                        output_char = None
                elif self.last_event.state == 1:
                    if last_duration >= DAH_LB:
                        # Consider the finished symbol a dah
                        self.symbol_buffer += SYMBOL_DAH
                        self.stats['dah'].update(last_duration)
                    else:
                        self.symbol_buffer += SYMBOL_DIT
                        self.stats['dit'].update(last_duration)
                    # We've finished a symbol, but we don't yet know if the character is done. So wait.
                    output_char = None
                    self.last_event = self.Event(0, event_time)
                elif self.last_event.state == -1:
                    # Continue to hold
                    output_char = None
                else:
                    raise AssertionError(f'Unexpected stored state: {self.last_event.state}')
            return output_char
        else:
            # We've only seen 0 for a long while, so just keep waiting
            return None

    @property
    def timing_report(self) -> str:
        stat_reports = {k: v.report for k, v in self.stats.items()}
        return pprint.pformat(stat_reports)
