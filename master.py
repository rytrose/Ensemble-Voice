from pyo import *
from pythonosc import udp_client, dispatcher, osc_server
import threading
import time
from utils import normalize_from_range
import random


class EnsembleVoice:
    def __init__(self, prompt_for_device=False):
        self.server = Server()
        self.server.deactivateMidi()
        self.server.boot()
        self.midi_device_name = ""
        self.midi_device_id = 1000
        self.midi_server = None

        self.setup_midi(prompt_for_device)

        self.landini_num_users = 0
        self.landini_user_names = []
        self.user_note_map = {}

        self.address = "127.0.0.1"
        self.local_port = 50505
        self.remote_port = 50506

        self.osc_client = udp_client.SimpleUDPClient(self.address, self.remote_port)

        self.dispatcher = dispatcher.Dispatcher()
        self.dispatcher.map("/landini/numUsers", self.landini_num_users_handler)
        self.dispatcher.map("/landini/userNames", self.landini_user_names_handler)
        self.dispatcher.set_default_handler(print)
        self.osc_server = osc_server.ThreadingOSCUDPServer((self.address, self.local_port), self.dispatcher)
        threading.Thread(target=self.osc_server.serve_forever).start()

        threading.Thread(target=self.check_for_new_users).start()

    def setup_midi(self, prompt_for_device):
        midi_devices = pm_get_input_devices()

        if prompt_for_device:
            print("Device names:")
            for device_name in midi_devices[0]:
                print("\t%s" % device_name)

            self.midi_device_name = input("Enter desired device: ")

        if self.midi_device_name in midi_devices[0]:
            index = midi_devices[0].index(self.midi_device_name)
            self.midi_device_id = midi_devices[1][index]
        elif self.midi_device_name == "":
            print("Listening to all available MIDI devices.")
        else:
            print("Could not find device '%s', listening to all available MIDI devices." % self.midi_device_name)

        self.midi_server = MidiListener(self.on_midi, mididev=self.midi_device_id)
        self.midi_server.start()

    def on_midi(self, status, note, velocity):
        current_notes = list(self.user_note_map.values())

        if velocity > 0:  # Note on
            if not note in current_notes:
                open_singers = list(filter(lambda n: self.user_note_map[n] is None, self.user_note_map.keys()))
                if not open_singers:
                    return
                new_singer = random.choice(open_singers)
                self.user_note_map[new_singer] = note
                self.send("/freq", note, users=new_singer)
                self.send("/mute", 0, users=new_singer)
        else:  # Note off
            note_singers = list(filter(lambda n: self.user_note_map[n] == note, self.user_note_map.keys()))
            if not note_singers:
                return
            for name in note_singers:
                self.user_note_map[name] = None
                self.send("/mute", 1, users=name)

    def send(self, address, args, protocol="/send/GD", users="allButMe"):
        if not isinstance(args, list):
            args = [args]

        self.osc_client.send_message(protocol, [users] + [address] + args)

    def check_for_new_users(self):
        while True:
            self.send("/null", [], protocol="/numUsers")
            time.sleep(0.2)

    def landini_num_users_handler(self, _, *args):
        if args:
            if self.landini_num_users == args[0] - 1:
                return

            self.landini_num_users = args[0] - 1
            print("Number of LANdini users: %d" % self.landini_num_users)
            self.send("/null", [], protocol="/userNames")

    def landini_user_names_handler(self, _, *args):
        if args == ():
            args = []

        if not isinstance(args, list):
            args = list(args)

        self.landini_user_names = args
        if self.landini_user_names:
            print("LANdini user names:")
            for name in self.landini_user_names:
                print("\t%s" % name)
                if not name in self.user_note_map.keys():
                    self.user_note_map[name] = None

        old_names = list(self.user_note_map.keys())
        for name in old_names:
            if not name in self.landini_user_names:
                self.user_note_map.pop(name, None)


if __name__ == "__main__":
    e = EnsembleVoice()
