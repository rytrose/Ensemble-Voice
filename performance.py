from pyo import *
from pretty_midi import hz_to_note_number
import mido
import threading
import socket
from pythonosc import udp_client
import argparse


class ErrorPerformance:
    def __init__(self, debug=False):
        self.debug = debug
        self.num_singers = 4
        self.measure_errors = []
        for _ in range(self.num_singers):
            self.measure_errors.append([])

        self.setup_audio()
        self.setup_midi()
        self.setup_input()
        self.setup_osc()

        self.current_freqs = [0, 0, 0, 0]
        self.error_checker_pattern = Pattern(self.check_error, time=0.1)
        self.error_checker_pattern.play()

    def setup_audio(self):
        pa_list_devices()

        if self.debug:
            self.server = Server()
            self.num_singers = 1
        else:
            self.server = Server(nchnls=4)
            self.input_output = input("Select audio device id: ")
            self.server.setInOutDevice(int(self.input_output))
        self.server.deactivateMidi()
        self.server.boot().start()

    def setup_midi(self):
        devices = mido.get_input_names()

        print("MIDI Input Devices:")
        for i, device in enumerate(devices):
            print("\t%d: %s" % (i, device))

        device_id = int(input("Select MIDI device id: "))
        port = mido.open_input(devices[device_id])
        threading.Thread(target=self.on_midi, args=(port,)).start()

    def setup_input(self):
        self.inputs = []
        for i in range(self.num_singers):
            input_obj = Input(i)
            self.inputs.append(input_obj)

        self.detects = []
        for i in range(self.num_singers):
            detect_obj = Yin(self.inputs[i])
            self.detects.append(detect_obj)

    def setup_osc(self):
        self.ip = socket.gethostbyname(socket.gethostname())
        print("Current ip:", self.ip)
        self.send_port = 5901
        self.listen_port = 5900
        self.client = udp_client.SimpleUDPClient(self.ip, self.send_port)

    def on_midi(self, port):
        while True:
            midi_message = port.receive()
            self.handle_message(midi_message)

    def handle_message(self, message):
        # print(message)
        if message.channel < 4:
            if message.type == 'note_on':
                self.current_freqs[message.channel] = message.note
            elif message.type == 'note_off':
                self.current_freqs[message.channel] = 0
        else:
            if message.channel == 4:
                if message.type == 'note_on':
                    # New measure
                    errors = []
                    for measure_error in self.measure_errors:
                        if len(measure_error) > 0:
                            errors.append(sum(measure_error) / len(measure_error))
                        else:
                            errors.append(0)
                    self.client.send_message("/error", errors)

                    self.measure_errors = []  # Reset measure error
                    for _ in range(self.num_singers):
                        self.measure_errors.append([])
                if message.type == 'control_change':
                    if message.value == 102:
                        self.client.send_message("/meter_changed", [])
                        self.client.send_message("/tempo", [102.4])
                    elif message.value == 73:
                        self.client.send_message("/tempo", [64])
                        self.client.send_message("/start", [])
                    

    def check_error(self):
        errors = []
        for i in range(self.num_singers):
            if self.current_freqs[i] != 0:
                input_hz = self.detects[i].get()
                input_midi = hz_to_note_number(input_hz)
                raw_difference = midi_chroma_difference(
                    self.current_freqs[i], input_midi)
                error = error_func(raw_difference)
                errors.append(error)
                self.measure_errors[i].append(error)
        self.client.send_message("/error_realtime", errors)


def error_func(val):
    error = 0.0
    if val < 1:
        error = 0.75 * (val ** 1.2)
    else:
        error = 0.75 + (0.25 * ((val - 1) / 11))
    return error


def midi_chroma_difference(note_0, note_1):
    abs_diff = abs(note_0 - note_1)
    if note_0 > note_1:
        while note_0 > note_1:
            note_0 -= 12
            new_diff = abs(note_0 - note_1)
            if new_diff < abs_diff:
                abs_diff = new_diff
            else:
                break
    else:
        while note_0 < note_1:
            note_0 += 12
            new_diff = abs(note_0 - note_1)
            if new_diff < abs_diff:
                abs_diff = new_diff
            else:
                break

    return abs_diff


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", default=False)
    args = parser.parse_args()
    print(args)
    e = ErrorPerformance(debug=args.debug)
