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

        self.player_ids = []
        self.id_note_map = {}
        self.current_notes = []

        self.address = input("Enter current IP: ")
        self.remote_address = input("Enter conductor patch IP: ")
        self.local_port = 54320
        self.remote_port = 54322

        self.osc_client = udp_client.SimpleUDPClient(self.remote_address, self.remote_port)

        self.dispatcher = dispatcher.Dispatcher()
        self.dispatcher.map("/players", self.players_handler)
        self.dispatcher.set_default_handler(print)
        self.osc_server = osc_server.ThreadingOSCUDPServer((self.address, self.local_port), self.dispatcher)
        threading.Thread(target=self.osc_server.serve_forever).start()

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
        # self.randomly_assign(note, velocity)
        self.current_notes.sort()

        if velocity > 0:  # Note on
            if not note in self.current_notes and len(self.current_notes) < 4:
                self.current_notes.append(note)
                self.current_notes.sort()
                self.assign_notes_to_voices()
        else:  # Note off
            self.current_notes.pop(self.current_notes.index(note))
            self.current_notes.sort()
            self.assign_notes_to_voices()

    def assign_notes_to_voices(self):
        for i in range(len(self.current_notes)):
            singer_id = i + 1
            if singer_id in self.id_note_map.keys():
                if self.id_note_map[singer_id] != self.current_notes[i]:
                    self.id_note_map[singer_id] = None
                    self.send("/mute", 1, user=singer_id)
                    self.id_note_map[singer_id] = self.current_notes[i]
                    self.send("/freq", self.id_note_map[singer_id], user=singer_id)
                    self.send("/mute", 0, user=singer_id)
        for singer_id in range(len(self.current_notes) + 1, 5):
            if singer_id in self.id_note_map.keys():
                self.id_note_map[singer_id] = None
                self.send("/mute", 1, user=singer_id)

    def send(self, address, args, user="allButMe"):
        if not isinstance(args, list):
            args = [args]

        self.osc_client.send_message("/send", [user] + [address] + args)

    def players_handler(self, _, *args):
        if args == ():
            args = []

        if not isinstance(args, list):
            args = list(args)

        ids = [int(singer_id) for singer_id in args]
        if -1 in ids:
            index = ids.index(-1)
            ids.pop(index)
        elif 0 in ids:
            index = ids.index(0)
            ids.pop(index)

        self.player_ids = ids
        if self.player_ids:
            for singer_id in self.player_ids:
                if not singer_id in self.id_note_map.keys():
                    self.id_note_map[singer_id] = None

        old_ids = list(self.id_note_map.keys())
        for singer_id in old_ids:
            if not singer_id in self.player_ids:
                self.id_note_map.pop(singer_id, None)

    def randomly_assign(self, note, velocity):
        current_notes = list(self.id_note_map.values())

        if velocity > 0:  # Note on
            if not note in current_notes:
                open_singers = list(filter(lambda singer_id: self.id_note_map[singer_id] is None, self.id_note_map.keys()))
                if not open_singers:
                    return
                new_singer = random.choice(open_singers)
                self.id_note_map[new_singer] = note
                self.send("/freq", note, user=new_singer)
                self.send("/mute", 0, user=new_singer)
        else:  # Note off
            note_singers = list(filter(lambda n: self.id_note_map[n] == note, self.id_note_map.keys()))
            if not note_singers:
                return
            for singer_id in note_singers:
                self.id_note_map[singer_id] = None
                self.send("/mute", 1, user=singer_id)


if __name__ == "__main__":
    e = EnsembleVoice(prompt_for_device=False)
