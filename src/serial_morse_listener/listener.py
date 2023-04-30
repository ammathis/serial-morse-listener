import serial
import serial.tools.list_ports
import signal
import sys
import time
import keyboard
import numpy as np
import argparse
from pathlib import Path
import threading
from typing import Optional, Type, Iterator
from types import TracebackType, FrameType

from serial_morse_listener.tone_generator import ToneGenerator
from serial_morse_listener.morse import MorseStreamProcessor


class MorseListener:
    def __init__(
            self,
            stop_event: threading.Event,
            wpm: int,
            serial_device: str = None,
            reads_per_second: int = 100,
            save_history_path: str = None,
            volume: float = 0.1
    ):
        self.stop_event = stop_event
        self.wpm = wpm
        self.volume = volume

        available_serial_devices = list(self.get_available_serial_devices('.*'))  # find all serial devices
        if serial_device is None:
            self.serial_device = self.choose_serial_device('usb')  # choose the first USB serial device
        else:
            self.serial_device = serial_device
        if self.serial_device not in available_serial_devices:
            raise RuntimeError(f'Specified serial device {self.serial_device} not found in available serial devices!')

        self.reads_per_second = reads_per_second
        if save_history_path is not None:
            self.save_history_path = Path(save_history_path)
        else:
            self.save_history_path = None

        self.processor = MorseStreamProcessor(wpm=wpm)
        
    def __enter__(self):
        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
    ) -> bool:
        self.shutdown()
        return False  # don't supress exceptions

    def shutdown(self):        
        # Write history
        if self.save_history_path is not None:
            history_np = np.array(self.processor.history_buffer, np.uint8)
            with self.save_history_path.open('wb') as outfile:
                np.save(outfile, history_np)
            print(f'Saved history to {self.save_history_path}')

        # Print timing stats
        print(f'Timing Stats:\n{self.processor.timing_report}')

    @staticmethod
    def get_available_serial_devices(pattern: str) -> Iterator[str]:
        return (p.device for p in serial.tools.list_ports.grep(pattern))

    @classmethod
    def choose_serial_device(cls, pattern: str) -> str:
        matching_devices = list(cls.get_available_serial_devices(pattern))
        if len(matching_devices) < 1:
            raise RuntimeError(f'No serial ports matching pattern "{pattern}" found to listen to!')

        chosen_device = matching_devices[0]
        return chosen_device

    def get_state(self) -> int:
        with serial.Serial(self.serial_device) as ser:
            return int(ser.cts)

    @staticmethod
    def write_keyboard_event(event: str):
        keyboard.write(event)

    def listen(self):
        print('Starting loop...')
        print(f'Listening at {self.processor.wpm}WPM. Dit duration is {self.processor.timing_unit}s.')

        # Set up audio (paused to start)
        audio_toggle = threading.Event()
        audio_toggle.clear()

        with ToneGenerator(toggle_switch=audio_toggle, volume=self.volume) as _:
            while not self.stop_event.is_set():
                # Get state
                state = self.get_state()

                # Trigger audio
                if state == 1:
                    audio_toggle.set()
                else:
                    audio_toggle.clear()

                # Process the signal
                output_char = self.processor.process_event(state)
                if output_char is not None:
                    self.write_keyboard_event(output_char)

                time.sleep(1.0/self.reads_per_second)


def do_listen(**kwargs):
    with MorseListener(**kwargs) as listener:
        listener.listen()


def main():
    parser = argparse.ArgumentParser(
        prog='Serial Morse Listener',
        description='This program listens to morse code inputs from a serial device, '
                    'and outputs corresponding keyboard events.',
        epilog='Morse code is so cool!'
        )
    parser.add_argument('wpm', type=float, help='Words-per-minute of listening')
    args = parser.parse_args()

    # Establish stop event
    stop_event = threading.Event()

    # Register sigint handler to trigger the stop_event
    def sigint_handler(sig: int, frame: Optional[FrameType]):
        _ = sig, frame
        print('\nYou pressed Ctrl+C! Shutting down...')
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    do_listen(stop_event=stop_event, wpm=args.wpm, reads_per_second=100)


if __name__ == '__main__':
    main()
