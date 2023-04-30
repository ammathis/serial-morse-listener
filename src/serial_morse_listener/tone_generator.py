import threading
import math
import time
import pyaudio
from pyaudio import PyAudio, Stream
import numpy as np
from typing import Optional, Type, Any, Tuple
from types import TracebackType


class ToneGenerator:
    def __init__(self, toggle_switch: threading.Event, volume: float = 0.1):
        # Generate a single period of samples
        if not (0.0 <= volume <= 1.0):
            raise ValueError(f'volume must be within [0.0,1.0]')
        self.volume = volume
        fs = 44100  # sampling rate, Hz, must be integer
        f = 441*1  # sine frequency, Hz
        period_length_float = fs/f
        self.period_length = math.floor(period_length_float)
        if self.period_length != period_length_float:
            raise AssertionError(f'Sampling rate {fs} and frequency {f} do not result in an integer period length!')
        samples = (np.sin(2 * np.pi * f/fs * np.arange(self.period_length))).astype(np.float32)
        samples = (self.volume * samples)
        self.samples = samples
        
        # Audio setup
        self.p: Optional[pyaudio.PyAudio] = None  # We'll populate this when starting the audio
        self.format_pyaudio, self.format_numpy = pyaudio.paFloat32, np.float32
        self.stream: Optional[Stream] = None
        self.stop_switch = threading.Event()
        self.toggle_switch = toggle_switch
        self.fs = fs
        self.cursor = 0
        self.last_seen_state = 0

    @property
    def toggle_is_set(self):
        return self.toggle_switch is None or self.toggle_switch.is_set()

    def read_samples(self, num_frames_to_read: int) -> np.ndarray:
        # Generate indexes for this batch plus the next one (to assign cursor)
        raw_ix = range(self.cursor, self.cursor + num_frames_to_read + 1)
        ix = [(i % self.period_length) for i in raw_ix]
        output = self.samples[ix[:-1]]  # the last ix is for the future cursor
        assert len(output) == num_frames_to_read
        assert output.dtype == self.format_numpy
        self.cursor = ix[-1]
        return output

    def get_next_samples(self, num_frames_to_read: int) -> np.ndarray:
        ideal_fade_duration = 20
        actual_fade_duration = min(ideal_fade_duration, num_frames_to_read)
        fade_pad_duration = num_frames_to_read - actual_fade_duration
        do_fade_in = False
        do_fade_out = True

        if self.toggle_is_set or self.last_seen_state == 1:
            output = self.read_samples(num_frames_to_read)

            if self.toggle_is_set:
                if self.last_seen_state == 0:
                    if do_fade_in:
                        # Fade in
                        fade = np.linspace(0, 1, actual_fade_duration)
                        fade = np.concatenate([fade, np.ones(fade_pad_duration)], axis=None)
                        output = output * fade
                    else:
                        # Abrupt start
                        pass
                else:
                    # Continue playing
                    pass

                self.last_seen_state = 1

            else:
                if do_fade_out:
                    # Fade out
                    fade = np.linspace(1, 0, actual_fade_duration, dtype=self.format_numpy)
                    fade = np.concatenate([fade, np.zeros(fade_pad_duration, dtype=self.format_numpy)], axis=None)
                else:
                    # Abrupt stop
                    fade = np.zeros(num_frames_to_read, dtype=self.format_numpy)
                output = output * fade

                self.last_seen_state = 0
                self.cursor = 0
        else:                
            # Silence
            output = np.zeros(num_frames_to_read, dtype=self.format_numpy)
            self.cursor = 0
        
        assert output.dtype == self.format_numpy
        return output

    def __enter__(self):
        self.start()
        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
    ) -> bool:
        self.shutdown()
        return False  # don't supress exceptions

    @staticmethod
    def serialize_audio_samples(data: np.ndarray):
        return data.tobytes()

    def audio_callback(self, in_data: Any, frame_count: int, time_info: Any, status: Any) -> Tuple[Optional[bytes], int]:
        _ = in_data, time_info, status
        if not self.stop_switch.is_set():
            data = self.get_next_samples(frame_count)
            return self.serialize_audio_samples(data), pyaudio.paContinue
        else:
            return None, pyaudio.paComplete

    def start(self):
        self.p = PyAudio()

        # for paFloat32 sample values must be in range [-1.0, 1.0]
        self.stream = self.p.open(
            format=self.format_pyaudio,
            channels=1,
            rate=self.fs,
            output=True,
            stream_callback=self.audio_callback
            )

    def shutdown(self):
        print('Shutting down tone generator')

        # Set the stop switch to trigger finishing of the audio
        self.stop_switch.set()

        # Wait for stream to finish
        if self.stream is not None:
            while self.stream.is_active():
                time.sleep(0.1)

            # Close the stream
            self.stream.close()

        # Release PortAudio system resources
        if self.p is not None:
            self.p.terminate()
