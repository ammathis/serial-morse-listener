# Serial Morse Code Listener

## Introduction

A program to:
* poll the CTS line of a serial port to get a binary state
  * (alternatively, listen for alt_r keypress on the keyboard)
* switch an audio tone on and off according to the input state
* interpret the signal of states over time as morse code
* and output the interpreted morse characters as keyboard events

## Running

Run the top-level program as follows:
```
python -m serial_morse_listener.listener <wpm>
```
The `wpm` argument sets the expected speed of input signals. An appropriate words-per-minute for (slow) beginners is 5.

Add the flag `-k` or `--keyboard` to listen for keyboard presses on the alt_r key instead of listening from the serial port. 

## Testing

There is an integration test in [tests/test_listener.py](tests/test_listener.py) which mocks the serial input and keyboard output, so that you can try the code out easily.

## Extending

With small changes to the `MorseListener` class in [listener.py](src/serial_morse_listener/listener.py), in particular the `get_state()` method, this program could easily be adapted to alternative streaming inputs, beyond serial port inputs.

The `MorseStreamProcessor` class in [morse.py](src/serial_morse_listener/morse.py) is written generically, to process streaming inputs via the `process_event()` method. This too lends itself to adaptation to alternative input events.
