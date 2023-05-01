import concurrent.futures
from unittest.mock import patch, MagicMock, call
import threading
import time
import numpy as np

from serial_morse_listener.listener import do_listen


@patch('serial_morse_listener.tone_generator.ToneGenerator.serialize_audio_samples')
@patch('serial_morse_listener.listener.MorseListener.write_keyboard_event')
@patch('serial_morse_listener.listener.MorseListener.get_serial_state')
@patch('serial_morse_listener.listener.MorseListener.get_available_serial_devices')
def test_listen(
        mock_get_available_serial_devices: MagicMock,
        mock_get_serial_state: MagicMock,
        mock_write_keyboard_event: MagicMock,
        mock_serialize_audio_samples: MagicMock
):

    mock_get_available_serial_devices.return_value = ['usb1']
    mock_get_serial_state.return_value = 0

    swallow_audio = True

    def side_effect_serialize_audio_samples(data: np.ndarray) -> bytes:
        if swallow_audio:
            # Return silence instead of audio
            return np.zeros(data.shape, dtype=data.dtype).tobytes()
        else:
            # Let the audio pass through
            return data.tobytes()

    mock_serialize_audio_samples.side_effect = side_effect_serialize_audio_samples

    stop_signal = threading.Event()
    wpm = 7
    volume = 0.1

    seen_exception = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(do_listen, wpm=wpm, stop_event=stop_signal, volume=volume)

        # Start with some silence
        time.sleep(0.5)
        # Simulate the sending of one dit then silence (i.e., an "e")
        mock_get_serial_state.return_value = 1
        time.sleep(0.1)
        mock_get_serial_state.return_value = 0
        time.sleep(0.5)
        # Now stop
        stop_signal.set()

        for future in concurrent.futures.as_completed([future]):
            try:
                _ = future.result()
            except Exception as e:
                seen_exception = e
            else:
                pass

    # Make sure we have no exceptions
    assert seen_exception is None

    # Make sure the test resulted in the expected simulated keyboard output
    expected_keyboard_calls = [call('e')]
    mock_write_keyboard_event.assert_called()
    mock_write_keyboard_event.assert_has_calls(expected_keyboard_calls, any_order=False)

    # Make sure the test resulted in the expected audio output (even if it was later intercepted)
    mock_serialize_audio_samples.assert_called()
    assert any(
        kall.args[0].max() >= volume  # some audio that reached the intended volume
        for kall in mock_serialize_audio_samples.call_args_list
    )
