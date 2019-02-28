from pyo import *
from pythonosc import udp_client, dispatcher, osc_server
import threading
import time
from utils import normalize_from_range
from pretty_midi import note_number_to_hz
import random


class Synth:
    def __init__(self, channel=0):
        self.adsr = Adsr()
        self.osc = RCOsc(mul=self.adsr)
        self.set_channel(channel)

    def set_channel(self, channel):
        self.osc.out(channel)

    @property
    def freq(self):
        return self.osc.freq

    @freq.setter
    def freq(self, value):
        self.osc.setFreq(value)

    def play(self):
        self.adsr.play()

    def stop(self):
        self.adsr.stop()


class EnsembleVoice:
    def __init__(self, prompt_for_device=False):
        self.setup_audio()
        # self.setup_midi(prompt_for_device)
        self.setup_dual_midi()

        self.player_ids = []
        self.id_note_map = {
            1: None,
            2: None,
            3: None,
            4: None
        }
        self.current_notes = []

        self.voice_notes = [None, None, None, None]

        # self.address = input("Enter current IP: ")
        # self.remote_address = input("Enter conductor patch IP: ")
        # self.local_port = 54320
        # self.remote_port = 54322
        #
        # self.osc_client = udp_client.SimpleUDPClient(self.remote_address, self.remote_port)
        #
        # self.dispatcher = dispatcher.Dispatcher()
        # self.dispatcher.map("/players", self.players_handler)
        # self.dispatcher.set_default_handler(print)
        # self.osc_server = osc_server.ThreadingOSCUDPServer((self.address, self.local_port), self.dispatcher)
        # threading.Thread(target=self.osc_server.serve_forever).start()

    def setup_audio(self):
        pa_list_devices()
        self.server = Server(nchnls=4)
        self.input_output = input("Select device: ")
        self.server.setInOutDevice(int(self.input_output))
        self.server.deactivateMidi()
        self.server.boot().start()
        self.midi_device_name = ""
        self.midi_device_id = 1000
        self.midi_server = None
        self.synths = [Synth(0), Synth(1), Synth(2), Synth(3)]

    def setup_midi(self, prompt_for_device):
        midi_devices = pm_get_input_devices()
        print(midi_devices)

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

    def setup_dual_midi(self):
        pm_list_devices()

        self.midi_device_0 = int(input("Enter first device id: "))
        self.midi_device_1 = int(input("Enter second device id: "))
        self.midi_device_ids = [self.midi_device_0, self.midi_device_1]

        self.midi_server = MidiListener(self.on_dual_midi, mididev=self.midi_device_ids, reportdevice=True)
        self.midi_server.start()

    def on_dual_midi(self, status, note, velocity, id):
        if not status in [144, 128]:
            return

        if (status == 144 and velocity == 0) or status == 128:  # Note Off
            self.assign_notes(self.midi_device_ids.index(id), note, False)

        else:  # Note On
            self.assign_notes(self.midi_device_ids.index(id), note, True)

    def assign_notes(self, id, note, on_or_off):
        note_0_ind = 2 * id
        note_1_ind = (2 * id) + 1
        note_0 = self.voice_notes[note_0_ind]
        note_1 = self.voice_notes[note_1_ind]

        if on_or_off:  # On
            if note_0 and note_1:
                if note_0 != note_1:
                    return  # If two different notes are held, throw out
                else:
                    if note > note_0:
                        self.voice_notes[note_1_ind] = note
                    else:
                        self.voice_notes[note_0_ind] = note
            else:
                self.voice_notes[note_0_ind] = note
                self.voice_notes[note_1_ind] = note
        else:  # Off
            if note_0 == note and note_1 == note:
                self.voice_notes[note_0_ind] = None
                self.voice_notes[note_1_ind] = None
            elif note_0 == note:
                self.voice_notes[note_0_ind] = note_1
            elif note_1 == note:
                self.voice_notes[note_1_ind] = note_0

        for i, note in enumerate(self.voice_notes):
            if note:
                self.synths[i].freq = note_number_to_hz(note)
                self.synths[i].play()
            else:
                self.synths[i].stop()

    def on_midi(self, status, note, velocity):
        # self.randomly_assign(note, velocity)
        self.voice_assignment(note, velocity)

    def voice_assignment(self, note, velocity):
        self.current_notes.sort()

        if 0 < velocity < 127:  # Note on | or (velocity == 127 and (note not in self.current_notes))
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
                    self.synths[singer_id - 1].stop()
                    # self.send("/mute", 1, user=singer_id)
                    self.id_note_map[singer_id] = self.current_notes[i]
                    self.synths[singer_id - 1].freq = note_number_to_hz(self.id_note_map[singer_id])
                    self.synths[singer_id - 1].play()
                    # self.send("/freq", self.id_note_map[singer_id], user=singer_id)
                    # self.send("/mute", 0, user=singer_id)
        for singer_id in range(len(self.current_notes) + 1, 5):
            if singer_id in self.id_note_map.keys():
                self.id_note_map[singer_id] = None
                self.synths[singer_id - 1].stop()
                # self.send("/mute", 1, user=singer_id)

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
                open_singers = list(
                    filter(lambda singer_id: self.id_note_map[singer_id] is None, self.id_note_map.keys()))
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
