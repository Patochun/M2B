"""

M2B - MIDI To Blender

Generate 3D objects animated from midifile

Author   : Patochun (Patrick M)
Mail     : ptkmgr@gmail.com
YT       : https://www.youtube.com/channel/UCCNXecgdUbUChEyvW3gFWvw
Create   : 2024-11-11
Version  : 8.0
Compatibility : Blender 4.0 and above

Licence used : GNU GPL v3
Check licence here : https://www.gnu.org/licenses/gpl-3.0.html

Comments : First version of M2B, a script to generate 3D objects animated from midifile

Usage : All parameters like midifile used and animation choices are hardcoded in the script

"""

import bpy
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
import sys

# Global blender objects
bDat = bpy.data
bCon = bpy.context
bScn = bCon.scene
bOps = bpy.ops

"""
MIDI module imported from https://github.com/JacquesLucke/animation_nodes
I was the initiator and participated in the implementation of the MIDI module in Animation Nodes
The final code was written by OMAR Emara and slightly modified here according to my needs
Additions:
    added noteMin & noteMax in track object 
    added notesUsed in track object
    added track only if it contains notes in tracks
    added trackIndexUsed vs trackIndex
Directly integrated here to avoid having to manage additional python modules
"""

from dataclasses import dataclass, field

def evaluateEnvelope(time, timeOn, timeOff, attackTime, attackInterpolation, decayTime, decayInterpolation, sustainLevel):
    # find either point in time for envelope or where in envelope the timeOff happened
    relativeTime = min(time, timeOff) - timeOn

    if relativeTime <= 0.0:
        return 0.0

    if relativeTime < attackTime:
        return attackInterpolation(relativeTime / attackTime)

    relativeTime = relativeTime - attackTime

    if relativeTime < decayTime:
        decayNormalized = decayInterpolation(1 - relativeTime/ decayTime)
        return decayNormalized * (1 - sustainLevel) + sustainLevel

    return sustainLevel

@dataclass
class MIDINote:
    channel: int = 0
    noteNumber: int = 0
    timeOn: float = 0
    timeOff: float = 0
    velocity: float = 0

    def evaluate(self, time, attackTime, attackInterpolation, decayTime, decayInterpolation, sustainLevel, 
        releaseTime, releaseInterpolation, velocitySensitivity):

        value = evaluateEnvelope(time, self.timeOn, self.timeOff, attackTime, attackInterpolation, decayTime, decayInterpolation, sustainLevel)

        if time > self.timeOff:
            value = value * releaseInterpolation(1 - ((time - self.timeOff) / releaseTime))

        # if velocity sensitivity is 25%, then take 75% of envelope and 25% of envelope with velocity
        return (1 - velocitySensitivity) * value + velocitySensitivity * self.velocity * value

    def copy(self):
        return MIDINote(self.channel, self.noteNumber, self.timeOn, self.timeOff, self.velocity)

from typing import List

@dataclass
class MIDITrackUsed:
    trackIndex: int = 0
    name: str = ""
    noteCount: int = 0
    notesUsed: List[int] = field(default_factory = list)

@dataclass
class MIDITrack:
    name: str = ""
    index: int = 0
    minNote: int = 1000
    maxNote: int = 0
    notes: List[MIDINote] = field(default_factory = list)
    notesUsed: List[int] = field(default_factory = list)

    def evaluate(self, time, channel, noteNumber, 
        attackTime, attackInterpolation, decayTime, decayInterpolation, sustainLevel, 
        releaseTime, releaseInterpolation, velocitySensitivity):

        noteFilter = lambda note: note.channel == channel and note.noteNumber == noteNumber
        timeFilter = lambda note: note.timeOff + releaseTime >= time >= note.timeOn
        filteredNotes = filter(lambda note: noteFilter(note) and timeFilter(note), self.notes)
        arguments = (time, attackTime, attackInterpolation, decayTime, decayInterpolation, 
            sustainLevel, releaseTime, releaseInterpolation, velocitySensitivity)
        return max((note.evaluate(*arguments) for note in filteredNotes), default = 0.0)

    def evaluateAll(self, time, channel, 
        attackTime, attackInterpolation, decayTime, decayInterpolation, sustainLevel,
        releaseTime, releaseInterpolation, velocitySensitivity):
        channelFilter = lambda note: note.channel == channel
        timeFilter = lambda note: note.timeOff + releaseTime >= time >= note.timeOn
        filteredNotes = list(filter(lambda note: channelFilter(note) and timeFilter(note), self.notes))
        arguments = (time, attackTime, attackInterpolation, decayTime, decayInterpolation, 
            sustainLevel, releaseTime, releaseInterpolation, velocitySensitivity)
        noteValues = []
        for i in range(128):
            filteredByNumberNotes = filter(lambda note: note.noteNumber == i, filteredNotes)
            value = max((note.evaluate(*arguments) for note in filteredByNumberNotes), default = 0.0)
            noteValues.append(value)
        return noteValues

    def copy(self):
        return MIDITrack(self.name, self.index, self.minNote, self.maxNote, [n.copy() for n in self.notes])

import struct

# Channel events
@dataclass
class NoteOnEvent:
    deltaTime: int
    channel: int
    note: int
    velocity: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        note = struct.unpack("B", memoryMap.read(1))[0]
        velocity = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, note, velocity)

@dataclass
class NoteOffEvent:
    deltaTime: int
    channel: int
    note: int
    velocity: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        note = struct.unpack("B", memoryMap.read(1))[0]
        velocity = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, note, velocity)

@dataclass
class NotePressureEvent:
    deltaTime: int
    channel: int
    note: int
    pressure: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        note = struct.unpack("B", memoryMap.read(1))[0]
        pressure = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, note, pressure)

@dataclass
class ControllerEvent:
    deltaTime: int
    channel: int
    controller: int
    value: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        controller = struct.unpack("B", memoryMap.read(1))[0]
        value = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, controller, value)

@dataclass
class ProgramEvent:
    deltaTime: int
    channel: int
    program: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        program = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, program)

@dataclass
class ChannelPressureEvent:
    deltaTime: int
    channel: int
    pressure: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        pressure = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, pressure)

@dataclass
class PitchBendEvent:
    deltaTime: int
    channel: int
    lsb: int
    msb: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, channel, memoryMap):
        lsb = struct.unpack("B", memoryMap.read(1))[0]
        msb = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, channel, lsb, msb)

# Only track events
@dataclass
class SequenceNumberEvent:
    deltaTime: int
    sequenceNumber: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        sequenceNumber = struct.unpack(">H", memoryMap.read(2))[0]
        return cls(deltaTime, sequenceNumber)

@dataclass
class TextEvent:
    deltaTime: int
    text: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        text = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, text)

@dataclass
class CopyrightEvent:
    deltaTime: int
    copyright: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        copyright = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, copyright)

@dataclass
class TrackNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, name)

@dataclass
class InstrumentNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, name)

@dataclass
class LyricEvent:
    deltaTime: int
    lyric: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        lyric = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, lyric)

@dataclass
class MarkerEvent:
    deltaTime: int
    marker: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        marker = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, marker)

@dataclass
class CuePointEvent:
    deltaTime: int
    cuePoint: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        cuePoint = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, cuePoint)

@dataclass
class ProgramNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, name)

@dataclass
class DeviceNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("latin-1")
        return cls(deltaTime, name)

@dataclass
class MidiChannelPrefixEvent:
    deltaTime: int
    prefix: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        prefix = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, prefix)

@dataclass
class MidiPortEvent:
    deltaTime: int
    port: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        port = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, port)

@dataclass
class EndOfTrackEvent:
    deltaTime: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        return cls(deltaTime)

@dataclass
class TempoEvent:
    deltaTime: int
    tempo: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        tempo = struct.unpack(">I", b"\x00" + memoryMap.read(3))[0]
        return cls(deltaTime, tempo)

@dataclass
class SmpteOffsetEvent:
    deltaTime: int
    hours: int
    minutes: int
    seconds: int
    fps: int
    fractionalFrames: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        hours = struct.unpack("B", memoryMap.read(1))[0]
        minutes = struct.unpack("B", memoryMap.read(1))[0]
        seconds = struct.unpack("B", memoryMap.read(1))[0]
        fps = struct.unpack("B", memoryMap.read(1))[0]
        fractionalFrames = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, hours, minutes, seconds, fps, fractionalFrames)

@dataclass
class TimeSignatureEvent:
    deltaTime: int
    numerator: int
    denominator: int
    clocksPerClick: int
    thirtySecondPer24Clocks: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        numerator = struct.unpack("B", memoryMap.read(1))[0]
        denominator = struct.unpack("B", memoryMap.read(1))[0]
        clocksPerClick = struct.unpack("B", memoryMap.read(1))[0]
        thirtySecondPer24Clocks = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, numerator, denominator, clocksPerClick, thirtySecondPer24Clocks)

@dataclass
class KeySignatureEvent:
    deltaTime: int
    flatsSharps: int
    majorMinor: int

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        flatsSharps = struct.unpack("B", memoryMap.read(1))[0]
        majorMinor = struct.unpack("B", memoryMap.read(1))[0]
        return cls(deltaTime, flatsSharps, majorMinor)

@dataclass
class SequencerEvent:
    deltaTime: int
    data: bytes

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        data = struct.unpack(f"{length}s", memoryMap.read(length))[0]
        return cls(deltaTime, data)

@dataclass
class SysExEvent:
    deltaTime: int
    data: bytes

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        data = struct.unpack(f"{length}s", memoryMap.read(length))[0]
        return cls(deltaTime, data)

@dataclass
class EscapeSequenceEvent:
    deltaTime: int
    data: bytes

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        data = struct.unpack(f"{length}s", memoryMap.read(length))[0]
        return cls(deltaTime, data)

import mmap
from os import SEEK_CUR

# A brief description of the MIDI specification:
# - http://www.somascape.org/midi/tech/spec.html
# A brief description of the MIDI File specification:
# - http://www.somascape.org/midi/tech/mfile.html
# A MIDI Binary Template:
# - https://www.sweetscape.com/010editor/repository/files/MIDI.bt
# A description of Running Status:
# - http://midi.teragonaudio.com/tech/midispec/run.htm

metaEventByType = {
    0x00 : SequenceNumberEvent,
    0x01 : TextEvent,
    0x02 : CopyrightEvent,
    0x03 : TrackNameEvent,
    0x04 : InstrumentNameEvent,
    0x05 : LyricEvent,
    0x06 : MarkerEvent,
    0x07 : CuePointEvent,
    0x08 : ProgramNameEvent,
    0x09 : DeviceNameEvent,
    0x20 : MidiChannelPrefixEvent,
    0x21 : MidiPortEvent,
    0x2F : EndOfTrackEvent,
    0x51 : TempoEvent,
    0x54 : SmpteOffsetEvent,
    0x58 : TimeSignatureEvent,
    0x59 : KeySignatureEvent,
    0x7F : SequencerEvent,
}

channelEventByStatus = {
    0x80 : NoteOffEvent,
    0x90 : NoteOnEvent,
    0xA0 : NotePressureEvent,
    0xB0 : ControllerEvent,
    0xC0 : ProgramEvent,
    0xD0 : ChannelPressureEvent,
    0xE0 : PitchBendEvent,
}

def unpackVLQ(memoryMap):
    total = 0
    while True:
        char = struct.unpack("B", memoryMap.read(1))[0]
        total = (total << 7) + (char & 0x7F)
        if not char & 0x80: break
    return total

def parseChannelEvent(deltaTime, status, memoryMap):
    channel = status & 0xF
    eventClass = channelEventByStatus[status & 0xF0]
    event = eventClass.fromMemoryMap(deltaTime, channel, memoryMap)
    if isinstance(event, NoteOnEvent) and event.velocity == 0:
        return NoteOffEvent(deltaTime, channel, event.note, 0)
    return event

def parseMetaEvent(deltaTime, memoryMap):
    eventType = struct.unpack("B", memoryMap.read(1))[0]
    length = unpackVLQ(memoryMap)
    eventClass = metaEventByType[eventType]
    event = eventClass.fromMemoryMap(deltaTime, length, memoryMap)
    return event

def parseSysExEvent(deltaTime, status, memoryMap):
    length = unpackVLQ(memoryMap)
    if status == 0xF0:
        return SysExEvent.fromMemoryMap(deltaTime, length, memoryMap)
    elif status == 0xF7:
        return EscapeSequenceEvent.fromMemoryMap(deltaTime, length, memoryMap)

def parseEvent(memoryMap, parseState):
    deltaTime = unpackVLQ(memoryMap)
    status = struct.unpack("B", memoryMap.read(1))[0]
    
    if status & 0x80: parseState.runningStatus = status
    else: memoryMap.seek(-1, SEEK_CUR)

    runningStatus = parseState.runningStatus
    if runningStatus == 0xFF:
        return parseMetaEvent(deltaTime, memoryMap)
    elif runningStatus == 0xF0 or runningStatus == 0xF7:
        return parseSysExEvent(deltaTime, runningStatus, memoryMap)
    elif runningStatus >= 0x80:
        return parseChannelEvent(deltaTime, runningStatus, memoryMap)

@dataclass
class MidiParseState:
    runningStatus: int = 0

def parseEvents(memoryMap):
    events = []
    parseState = MidiParseState()
    while True:
        event = parseEvent(memoryMap, parseState)
        events.append(event)
        if isinstance(event, EndOfTrackEvent): break
    return events

def parseTrackHeader(memoryMap):
    identifier = memoryMap.read(4).decode('latin-1')
    chunkLength = struct.unpack(">I", memoryMap.read(4))[0]
    return chunkLength

@dataclass
class MidiTrack:
    events: List

    @classmethod
    def fromMemoryMap(cls, memoryMap):
        chunkLength = parseTrackHeader(memoryMap)
        events = parseEvents(memoryMap)
        return cls(events)

def parseHeader(memoryMap):
    identifier = memoryMap.read(4).decode('latin-1')
    chunkLength = struct.unpack(">I", memoryMap.read(4))[0]
    midiFormat = struct.unpack(">H", memoryMap.read(2))[0]
    tracksCount = struct.unpack(">H", memoryMap.read(2))[0]
    ppqn = struct.unpack(">H", memoryMap.read(2))[0]
    return midiFormat, tracksCount, ppqn

def parseTracks(memoryMap, tracksCount):
    return [MidiTrack.fromMemoryMap(memoryMap) for i in range(tracksCount)]

@dataclass
class MidiFile:
    midiFormat: int
    ppqn: int
    tempo: int
    tracks: List[MidiTrack]

    @classmethod
    def fromFile(cls, filePath):
        with open(filePath, "rb") as f:
            memoryMap = mmap.mmap(f.fileno(), 0, access = mmap.ACCESS_READ)
            midiFormat, tracksCount, ppqn = parseHeader(memoryMap)
            tracks = parseTracks(memoryMap, tracksCount)
            memoryMap.close()
            tempo = -1 # initialisation
            return cls(midiFormat, ppqn, tempo, tracks)

# Notes:
# - If no tempo event was found, a default tempo event of tempo 500,000 will be
#   inserted at time 0. The same applies if no tempo event happens at time 0,
#   this is done to guarantee any channel event will be preceded by a tempo event.
# - MIDI format 1 is a special format where the first track only contains tempo
#   events that represents the tempo map of all other tracks. So the code is
#   written accordingly.

@dataclass
class TempoEventRecord:
    timeInTicks: int
    timeInSeconds: int
    tempo: int

class TempoMap:
    def __init__(self, midiFile):
        self.ppqn = midiFile.ppqn
        self.midiFormat = midiFile.midiFormat
        self.computeTempoTracks(midiFile)

    def computeTempoTracks(self, midiFile):
        tracks = midiFile.tracks
        if midiFile.midiFormat == 1: tracks = tracks[0:1]
        self.tempoTracks = [[] * len(tracks)]
        for trackIndex, track in enumerate(tracks):
            timeInTicks = 0
            timeInSeconds = 0
            tempoEvents = self.tempoTracks[trackIndex]
            for event in track.events:
                timeInTicks += event.deltaTime
                timeInSeconds = self.timeInTicksToSeconds(trackIndex, timeInTicks)
                if not isinstance(event, TempoEvent): continue
                tempoEvents.append(TempoEventRecord(timeInTicks, timeInSeconds, event.tempo))

    def timeInTicksToSeconds(self, trackIndex, timeInTicks):
        trackIndex = trackIndex if self.midiFormat != 1 else 0
        tempoEvents = self.tempoTracks[trackIndex]
        matchFunction = lambda event: event.timeInTicks <= timeInTicks
        matchedEvents = filter(matchFunction, reversed(tempoEvents))
        tempoEvent = next(matchedEvents, TempoEventRecord(0, 0, 500_000))
        microSecondsPerTick = tempoEvent.tempo / self.ppqn
        secondsPerTick = microSecondsPerTick / 1_000_000
        elapsedSeconds = (timeInTicks - tempoEvent.timeInTicks) * secondsPerTick
        return tempoEvent.timeInSeconds + elapsedSeconds

# Notes:
# - It is possible for multiple consecutive Note On Events to happen on the same
#   channel and note number. The `numberOfNotes` member in NoteOnRecord represents
#   the number of such consecutive events. Note Off Events decrement that number
#   and are only considered when that number becomes 1.
# - The MIDI parser takes care of running-status Note On Events with zero velocity
#   so the code needn't check for that.

@dataclass
class NoteOnRecord:
    ticks: int
    time: float
    velocity: float
    numberOfNotes: int = 1

class TrackState:
    def __init__(self):
        self.timeInTicks = 0
        self.timeInSeconds = 0
        self.noteOnTable = dict()

    def updateTime(self, trackIndex, tempoMap, deltaTime):
        self.timeInTicks += deltaTime
        self.timeInSeconds = tempoMap.timeInTicksToSeconds(trackIndex, self.timeInTicks)

    def recordNoteOn(self, event):
        key = (event.channel, event.note)
        if key in self.noteOnTable:
            self.noteOnTable[key].numberOfNotes += 1
        else:
            self.noteOnTable[key] = NoteOnRecord(self.timeInTicks, self.timeInSeconds, event.velocity / 127)

    def getCorrespondingNoteOnRecord(self, event):
        key = (event.channel, event.note)
        noteOnRecord = self.noteOnTable[key]
        if noteOnRecord.numberOfNotes == 1:
            del self.noteOnTable[key]
            return noteOnRecord
        else:
            noteOnRecord.numberOfNotes -= 1
            return None

def readMIDIFile(path):
    midiFile = MidiFile.fromFile(path)
    tempoMap = TempoMap(midiFile)
    # set tempo to tempo value if fixe for all midifile
    if len(tempoMap.tempoTracks) == 1:
        tempo = tempoMap.tempoTracks[0][0].tempo
    else:
        tempo = 0
    midiFile.tempo = tempo
    workingTracks = []
    fileTracks = midiFile.tracks if midiFile.midiFormat != 1 else midiFile.tracks[1:]
    trackIndexUsed = 0
    for trackIndex, track in enumerate(fileTracks):
        notes = []
        notesUsed = []
        trackName = ""
        trackState = TrackState()
        minNote = 1000
        minDurationInTicks = 1000000
        maxNote = 0
        for event in track.events:
            trackState.updateTime(trackIndex, tempoMap, event.deltaTime)
            if isinstance(event, TrackNameEvent):
                trackName = event.name
            elif isinstance(event, NoteOnEvent):
                trackState.recordNoteOn(event)
                minNote = min(minNote, event.note)
                maxNote = max(maxNote, event.note)
                # add note in notesUsed if not already
                if event.note not in notesUsed:
                    notesUsed.append(event.note)
            elif isinstance(event, NoteOffEvent):
                noteOnRecord = trackState.getCorrespondingNoteOnRecord(event)
                if noteOnRecord is None: continue
                startTime = noteOnRecord.time
                velocity = noteOnRecord.velocity
                endTime = trackState.timeInSeconds
                notes.append(MIDINote(event.channel, event.note, startTime, endTime, velocity))
                minDurationInTicks = min(minDurationInTicks, trackState.timeInTicks - noteOnRecord.ticks) # not used yet
        # add track only if exist notes inside
        if bool(notesUsed):
            workingTracks.append(MIDITrack(trackName, trackIndexUsed, minNote, maxNote, notes, notesUsed))
            trackIndexUsed += 1
    # if midifile format is 0 then explode all channels from track 0 in several track
    if midiFile.midiFormat == 0:
        trackIndexUsed = 0
        tracks = []
        for channel in range(16):
            notes = []
            notesUsed = []
            minNote = 1000
            maxNote = 0
            for note in workingTracks[0].notes:
                if note.channel == channel:
                    notes.append(note)
                    minNote = min(minNote, note.noteNumber)
                    maxNote = max(maxNote, note.noteNumber)
                    if note.noteNumber not in notesUsed:
                        notesUsed.append(note.noteNumber)
            if bool(notesUsed):
                tracks.append(MIDITrack(workingTracks[0].name+"-ch"+str(channel), trackIndexUsed, minNote, maxNote, notes, notesUsed))
                trackIndexUsed += 1
    # else, midifile format 1, 2 then use workingTracks previously created
    else:
        tracks = workingTracks
            
    return midiFile, tempoMap, tracks

"""
End of Module MIDI for importation
"""

"""
Start of original code
"""

# Import necessary modules
import os  # Provides functions for interacting with the operating system
import time  # Provides time-related functions
import math  # Provides mathematical functions
import random  # Provides functions for generating random numbers

# write to screen and log
def wLog(toLog):
    print(toLog)
    flog.write(toLog+"\n")

# Define blender unit system
def setBlenderUnits(unitScale=0.01, lengthUnit="CENTIMETERS"):
    bScn.unit_settings.system = 'METRIC'
    bScn.unit_settings.system_rotation = 'DEGREES'
    bScn.unit_settings.length_unit = lengthUnit
    bScn.unit_settings.scale_length = unitScale

    for area in bCon.screen.areas:
        if area.type == 'VIEW_3D':  # check if it is a 3D view
            for space in area.spaces:
                if space.type == 'VIEW_3D':  # check 3D space in editor
                    # Modifier l'échelle de la grille
                    space.overlay.grid_scale = 0.01
                    space.clip_end = 10000.0
                    break

# Research about a collection
def find_collection(context, item):
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection

# Maximize aera view in all windows.
# type = VIEW_3D
# type = OUTLINER
def GUI_maximizeAeraView(type):
    for window in bCon.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == type:
                with bCon.temp_override(window=window, area=area):
                    bpy.ops.screen.screen_full_area()
                break

def toggle_collection_collapse(state):
    area = next(a for a in bCon.screen.areas if a.type == "OUTLINER")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bCon.temp_override(area=area, region=region):
        bOps.outliner.show_hierarchy("INVOKE_DEFAULT")
        for i in range(state):
            # Expand/Collapse all items
            bOps.outliner.expanded_toggle()
    area.tag_redraw()
    # https://projects.blender.org/blender/blender/issues/125522
    
def collapseAllCollectionInOutliner():
    for window in bCon.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "OUTLINER":
                with bCon.temp_override(window=window, area=area):
                    bpy.ops.outliner.expanded_toggle()
                break

    wLog("No OUTLINER area found in the current context.")
       
# Create collection
def create_collection(collection_name, parent_collection):
    # delete if exist
    if collection_name in bDat.collections:
        collection = bDat.collections[collection_name]
        for ob in collection.objects:
            bDat.objects.remove(ob, do_unlink=True)
        bDat.collections.remove(collection)
    # create a new one
    new_collection = bDat.collections.new(collection_name)
    parent_collection.children.link(new_collection)

    return new_collection

# Delete all objects from a collection
def clearCollection(collection):
    for obj in list(collection.objects):
        bDat.objects.remove(obj, do_unlink=True)

def purgeUnusedDatas():
    """
    Purge all orphaned (unused) data in the current Blender file.
    This includes unused objects, materials, textures, collections, particles, etc.
    """
    
    # Purge orphaned objects, meshes, lights, cameras, and other data
    # bOps.outliner.orphan_data()
    
    # Force update in case orphan purge needs cleanup
    # bCon.view_layer.update()
    
    purgedItems = 0

    # Clean orphaned objects
    for obj in bDat.objects:
        if not obj.users:
            bDat.objects.remove(obj)
            purgedItems += 1

    # Clean orphaned curves
    for curve in bDat.curves:
        if not curve.users:
            bDat.curves.remove(curve)
            purgedItems += 1
    
    # Clear orphaned collections
    for collection in bDat.collections:
        if not collection.objects:
            # If the collection has no objects, remove it
            bDat.collections.remove(collection)
            purgedItems += 1

    # Clean orphaned meshes
    for mesh in bDat.meshes:
        if not mesh.users:
            bDat.meshes.remove(mesh)
            purgedItems += 1
    
    # Clean orphaned materials
    for mat in bDat.materials:
        if not mat.users:
            bDat.materials.remove(mat)
            purgedItems += 1

    # Clean orphaned textures
    for tex in bDat.textures:
        if not tex.users:
            bDat.textures.remove(tex)
            purgedItems += 1
    
    # Clean orphaned images
    for img in bDat.images:
        if not img.users:
            bDat.images.remove(img)
            purgedItems += 1
            
    # Clean orphaned particle settings
    for ps in bDat.particles:
        if not ps.users:
            bDat.particles.remove(ps)
            purgedItems += 1
            
    # Clean orphaned node groups
    for ng in bDat.node_groups:
        if not ng.users:
            bDat.node_groups.remove(ng)
            purgedItems += 1
            
    # Clean orphaned actions
    for action in bDat.actions:
        if not action.users:
            bDat.actions.remove(action)
            purgedItems += 1

    # Clean orphaned collections
    for collection in bDat.collections:
        if not collection.users:
            bDat.collections.remove(collection)
            purgedItems += 1

    # Clean orphaned sounds
    for sound in bDat.sounds:
        if not sound.users:
            bDat.sounds.remove(sound)
            purgedItems += 1

    # Log the results
    wLog("Purging complete. "+str(purgedItems)+" Orphaned datas cleaned up.")

def createCustomAttributes(obj):
    # Add custom attributes
    obj["baseColor"] = 0.0  # Base color as a float
    obj.id_properties_ui("baseColor").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Color factor for base Color (0 to 1)"
    )
    obj["emissionColor"] = 0.0  # Emission color as a float
    obj.id_properties_ui("emissionColor").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Color factor for the emission (0 to 1)"
    )
    obj["emissionStrength"] = 0.0  # Emission strength as a float
    obj.id_properties_ui("emissionStrength").update(
        min=0.0,  # Minimum value
        soft_min=0.0,  # Soft minimum for UI
        soft_max=50.0,  # Soft maximum for UI
        description="Strength of the emission"
    )
    obj["alpha"] = 1.0  # Emission strength as a float
    obj.id_properties_ui("alpha").update(
        min=0.0, # Minimum value
        max=1.0, # Maximum value
        soft_min=0.0,  # Soft minimum for UI
        soft_max=50.0,  # Soft maximum for UI
        description="Alpha transparency"
    )
    
    return

# Create Rectangular Plane
def createRectangularPlane(collection, name, material, width=1, height=1, location=(0, 0, 0)):
    bOps.mesh.primitive_plane_add(size=1, location=location)
    plane = bCon.active_object
    plane.name = name
    plane.scale[0] = width  # Adjust width (X)
    plane.scale[1] = height  # Adjust heigth (Y)
    plane.data.materials.append(material)
    createCustomAttributes(plane)
    # bOps.object.transform_apply(location=True, rotation=False, scale=True)    
    collect_to_unlink = find_collection(bCon, plane)
    collection.objects.link(plane)
    collect_to_unlink.objects.unlink(plane)
    return plane

# Create ico Sphere
def addIcoSphere(collection, name, material, location=(0,0,0), radius=1.0):
    # Add an icosphere at the specified location
    bOps.mesh.primitive_ico_sphere_add(radius=radius, location=location)
    sphere = bCon.active_object
    sphere.name = name
    sphere.location = location
    sphere.data.materials.append(material)
    createCustomAttributes(sphere)
    # Move the icosphere to the specified collection
    collect_to_unlink = find_collection(bCon, sphere)
    collection.objects.link(sphere)
    collect_to_unlink.objects.unlink(sphere)
    return sphere

# Create a new Bézier circle
def addBezierCircle(collection, name, location=(0,0,0), radius=1.0):
    bezierCircle = bOps.curve.primitive_bezier_circle_add
    bezierCircle(location=location, radius=radius)
    bezierCircleObj = bCon.object
    bezierCircleObj.name = name
    bezierCircleObj.data.resolution_u = 12  # Default is 12, increase for smoother curves
    # Move the bezierCircle to the specified collection
    collect_to_unlink = find_collection(bCon, bezierCircleObj)
    collection.objects.link(bezierCircleObj)
    collect_to_unlink.objects.unlink(bezierCircleObj)
    return bezierCircleObj

# Create Rectangular Cube
def addCube(collection, name, material, bevel=False, location=(0,0,0), scale=(1,1,1)):
    bOps.mesh.primitive_cube_add(size=1, location=location)
    cube = bCon.active_object
    cube.name = name
    cube.location = location
    cube.scale = scale
    cube.data.materials.append(material)
    createCustomAttributes(cube)
    if bevel:
        bOps.object.modifier_add(type="BEVEL")
        bOps.object.modifier_apply(modifier="BEVEL")
    collect_to_unlink = find_collection(bCon, cube)
    collection.objects.link(cube)
    collect_to_unlink.objects.unlink(cube)
    # bOps.object.transform_apply(location=True, rotation=False, scale=True)    
    return cube

# Create a new cylinder object
def addCylinder(collection, name, material, location, radius, height):
    bOps.mesh.primitive_cylinder_add(radius=radius, depth=height, location=location)
    cylinder = bCon.active_object
    cylinder.name = name
    cylinder.location = location
    cylinder.scale = (radius, radius, height)
    cylinder.data.materials.append(material)
    createCustomAttributes(cylinder)
    collect_to_unlink = find_collection(bCon, cylinder)
    collection.objects.link(cylinder)
    collect_to_unlink.objects.unlink(cylinder)
    return cylinder

# Create Duplicate Instance of an Object with an another name
def createDuplicateLinkedObject(collection, originalObject, name):
    # Créer une copie liée de l'objet original
    linkedObject = originalObject.copy()
    linkedObject.name = name
    # Ajouter l'instance à la collection spécifiée
    collection.objects.link(linkedObject)
    return linkedObject

# Set color from Trackindex and TracksCount
def colorFromIndex(trackIndex, tracksCount):
    colorTrack = (trackIndex + 1) / (len(tracks) + 1) # color for track
    colorTrack = (int(colorTrack * 255) ^ 0xAA) /255 # XOR operation to get a different color
    # hue = trackIndex / tracksCount  # Uniform hue
    return colorTrack

# Define color from note number when sharp or flat
def colorFromNoteNumber(noteNumber):
    if noteNumber in [1, 3, 6, 8, 10]:
        return 0.0  # Black note
    else:
        return 0.01 # White note

# Set a new material with Object link mode to object
# If typeAnim contains "Light", material needs to be independent
def setMaterialWithObjectLink(obj, typeAnim, color):

    # If typeAnim contains "Light" => create a new material independent of shared mesh
    # else do nothing, keep material from obj
    if "Light" in typeAnim:
        # Ensure material is independent of shared mesh
        # Create new material
        matNew = bDat.materials.new(name="Material-" + obj.name)
        matNew.use_nodes = True
        # Set material with base color
        principled = matNew.node_tree.nodes.get("Principled BSDF")
        if principled is not None:
            principled.inputs["Base Color"].default_value = color
        if len(obj.material_slots) == 0:
            obj.data.materials.append(matNew)  # Add a material slot if it doesn't exist
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = matNew  # Assign the material to the object
    # else:
        # Material can be linked to the mesh (default behavior)
        # if len(obj.material_slots) == 0:
        #     obj.data.materials.append(matNew)  # Add a material slot if it doesn't exist
        # obj.material_slots[0].link = 'DATA'  # Link material to mesh data
#        obj.material_slots[0].material = matNew  # Assign the material to the mesh

import colorsys

# Return a list of color r,g,b,a dispatched
def generateHSVColors(nSeries):
    colors = []
    for i in range(nSeries):
        hue = i / nSeries  # uniform space
        saturation = 0.8    # Saturation high for vibrant color
        value = 0.9         # High luminosity
        r,g,b = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append((r,g,b, 1.0))
    return colors

# Boolean Modifier
def booleanModifier(objHost, operandeGuest, typeModifier = "DIFFERENCE"):
    # Ajouter un modificateur booléen pour retirer la géométrie
    bool_modifier = objHost.modifiers.new(name="Boolean", type='BOOLEAN')
    bool_modifier.operation = typeModifier

    if isinstance(operandeGuest, bpy.types.Object):
        operandType = 'OBJECT'
    elif isinstance(operandeGuest, bpy.types.Collection):
        operandType = 'COLLECTION'
    bool_modifier.operand_type = operandType

    if operandType == "OBJECT":
        bool_modifier.object = operandeGuest
    elif operandType == "COLLECTION":
        bool_modifier.collection = operandeGuest

    # Appliquer le modificateur
    bCon.view_layer.objects.active = objHost
    bOps.object.modifier_apply(modifier=bool_modifier.name)

def clamp(value, min_val, max_val):
    """Clamp a value to ensure it's between min_val and max_val."""
    return max(min_val, min(value, max_val))

def smoothstep(edge0, edge1, x):
    """
    Smoothstep function for smooth interpolation.
    Produces a smooth curve from 0 to 1 between edge0 and edge1.
    """
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3 - 2 * t)

def sigmoid(x, k=10):
    """Apply a sigmoid function to a value."""
    return 1 / (1 + math.exp(-k * (x - 0.5)))

# Affect obj with note event accordingly to typeAnim and data from note
# index = 2 mean Z axis
def noteAnimate(Obj, typeAnim, note, previousNote, nextNote, colorTrack):

    eventLenMove = math.ceil(fps * 0.1) # Length (in frames) before and after event for moving to it, 10% of FPS

    frameTimeOn = int(note.timeOn * fps)
    frameTimeOff = int(note.timeOff * fps)
    frameLength = frameTimeOff - frameTimeOn

    # reevaluate note length if too short
    if (frameTimeOff - frameTimeOn) < 3:
        frameTimeOff = frameTimeOn + 2
        eventLenMove = 1

    # reevaluate eventLenMove length if too long
    if (eventLenMove * 2) >= (frameTimeOff - frameTimeOn):
        eventLenMove = int((frameTimeOff - frameTimeOn) / 2)

    # Calculate the frame time off for the previous note
    if previousNote:
        frameTimeOffPrevious = int(previousNote.timeOff * fps)
    else:
        frameTimeOffPrevious = frameTimeOn

    # Calculate the frame time on for the next note
    if nextNote:
        frameTimeOnNext = int(nextNote.timeOn * fps)
    else:
        frameTimeOnNext = frameTimeOff

    # Exclude animation if the note is interlaced to the previous or next note
    if frameTimeOn < frameTimeOffPrevious or frameTimeOff > frameTimeOnNext:
        return

    frameT1 = frameTimeOn
    frameT2 = frameTimeOn + eventLenMove
    frameT3 = frameTimeOff - eventLenMove
    frameT4 = frameTimeOff

    # Split the typeAnim string by commas to handle multiple types of animation
    types = typeAnim.split(',')
    for animation_type in types:
        match animation_type.strip():  # Remove extra spaces and match each animation type
            case "ZScale":
                velocity = 8 * note.velocity
                # set initial ZScale cube before acting (T1)
                Obj.scale.z = 1
                Obj.location.z = 0
                Obj.keyframe_insert(data_path="scale", index=2, frame=frameT1)  # before upscaling
                Obj.keyframe_insert(data_path="location", index=2, frame=frameT1)
                # Upscale cube at noteNumber on timeOn (T2)
                Obj.scale.z = velocity
                Obj.location.z = ((velocity - 1) / 2)
                Obj.keyframe_insert(data_path="scale", index=2, frame=frameT2)  # upscaling
                Obj.keyframe_insert(data_path="location", index=2, frame=frameT2)
                # set actual scale cube before acting (T3)
                Obj.scale.z = velocity
                Obj.location.z = ((velocity - 1) / 2)
                Obj.keyframe_insert(data_path="scale", index=2, frame=frameT3) # before downscaling
                Obj.keyframe_insert(data_path="location", index=2, frame=frameT3)
                # downscale cube at noteNumber on timeOff (T4)
                Obj.scale.z = 1
                Obj.location.z = 0
                Obj.keyframe_insert(data_path="scale", index=2, frame=frameT4)  # downscaling
                Obj.keyframe_insert(data_path="location", index=2, frame=frameT4)
            case "Light": # velocity animate light from blue to red
                brightness = note.velocity * 10 # 2 ** (velocity ** 10)
                # Constrain velocityBlueToRed based on note.velocity
                minValue = 0.02
                maxValue = 0.4
                
                # Push values away from the median towards the edges
                if note.velocity < 0.5:
                    adjustedVelocity = 2 * (note.velocity ** 2)
                else:
                    adjustedVelocity = 1 - 2 * ((1 - note.velocity) ** 2)
                
                velocityBlueToRed = minValue + (maxValue - minValue) * adjustedVelocity
                # set initial lighing before note On (T1)
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT1)
                # Upscale lighting on timeOn (T2)
                Obj["emissionColor"] = velocityBlueToRed
                Obj["emissionStrength"] = brightness
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT2)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT2)
                # Keep actual lighting before note Off (T3)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT3)
                # reset ligthing to initial state on timeOff (T4)
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT4)
            case "MultiLight":
                brightness = 5 + note.velocity * 10
                # set initial lighing before note On (T1)
                Obj["emissionColor"] = colorTrack
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT1)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT1)
                # Upscale lighting on timeOn (T2)
                Obj["emissionColor"] = colorTrack
                Obj["emissionStrength"] = brightness
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT2)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT2)
                # Keep actual lighting before note Off (T3)
                Obj["emissionColor"] = colorTrack
                Obj["emissionStrength"] = brightness
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT3)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT3)
                # reset ligthing to initial state on timeOff (T4)
                Obj["emissionColor"] = colorTrack
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT4)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT4)
            case "Spread":
                posZ = note.velocity * 30
                radius = min(frameLength / 2, 5)
                # set initial spread before note On (T1)
                Obj.location.z = posZ
                Obj.scale = (0,0,0)
                Obj["emissionStrength"] = 0
                Obj.keyframe_insert(data_path="location", index=2, frame=frameT1)
                Obj.keyframe_insert(data_path="scale", frame=frameT1)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT1)
                densityCloud = Obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densityCloud"].identifier
                Obj.modifiers["SparklesCloud"][densityCloud] = note.velocity / 3
                Obj.keyframe_insert(data_path="modifiers[\"SparklesCloud\"][\""+densityCloud+"\"]", frame=frameT1)
                densitySeed = Obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
                Obj.modifiers["SparklesCloud"][densitySeed] = random.randint(0, 1000)
                Obj.keyframe_insert(data_path="modifiers[\"SparklesCloud\"][\""+densitySeed+"\"]", frame=frameT1)
                # Spread on timeOn (T2)
                Obj.scale = (radius,radius,radius)
                Obj["emissionStrength"] = 20
                Obj.keyframe_insert(data_path="scale", frame=frameT2)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT2)
                # reset spread on timeOff (T4)
                Obj.scale = (0,0,0)
                Obj["emissionStrength"] = 0
                Obj.keyframe_insert(data_path="scale", frame=frameT4)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT4)
                densitySeed = Obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
                Obj.modifiers["SparklesCloud"][densitySeed] = random.randint(0, 1000)
                Obj.keyframe_insert(data_path="modifiers[\"SparklesCloud\"][\""+densitySeed+"\"]", frame=frameT4)
            case _:
                wLog("I don't now anything about "+typeAnim)

# Parse a formated range in string and return a liste of values
def parseRangeFromTracks(rangeStr):
    """
        Parses a range string and returns a list of numbers.
        Example input: "1-5,7,10-12"
        Example output: [1, 2, 3, 4, 5, 7, 10, 11, 12]
    """

    numbers = []
    # Divide string in individuals parts
    segments = rangeStr.split(',')

    for segment in segments:
        match = re.match(r'^(\d+)-(\d+)$', segment)
        if match:  # Case of range like "1-16"
            start, end = map(int, match.groups())
            numbers.extend(range(start, end + 1))
        elif re.match(r'^\d+$', segment):  # Case of single number
            numbers.append(int(segment))
        else:
            raise ValueError(f"Format non valide : {segment}")

    wLog("Track filter used = "+str(numbers))

    # Evaluate noteMin, noteMax and octaveCount from effective range
    noteMin = 1000
    noteMax = 0
    effectiveTrackCount = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in numbers:
            continue
        
        effectiveTrackCount += 1
        noteMin = min(noteMin, track.minNote)
        noteMax = max(noteMax, track.maxNote)

    octaveCount = (noteMax // 12) - (noteMin // 12) + 1

    return numbers, noteMin, noteMax, octaveCount, effectiveTrackCount

# Create a global material with custom object attributes for base color, emission color and emission strength
def CreateMatGlobalCustom():
    materialName = "GlobalCustomMaterial"
    if materialName not in bDat.materials:
        mat = bDat.materials.new(name=materialName)
        mat.use_nodes = True
    else:
        mat = bDat.materials[materialName]

    # Configure the material nodes
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Add necessary nodes
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (600, 0)

    principledBSDF = nodes.new(type="ShaderNodeBsdfPrincipled")
    principledBSDF.location = (200, 0)

    attributeBaseColor = nodes.new(type="ShaderNodeAttribute")
    attributeBaseColor.location = (-400, 100)
    attributeBaseColor.attribute_name = "baseColor"
    attributeBaseColor.attribute_type = 'OBJECT'

    colorRampBase = nodes.new(type="ShaderNodeValToRGB")
    colorRampBase.location = (-200, 100)
    colorRampBase.color_ramp.interpolation = 'CARDINAL'  # Ensure linear interpolation
    colorRampBase.color_ramp.elements.new(0.01)  # Add a stop at 0.01
    colorRampBase.color_ramp.elements.new(0.02)  # Add a stop at 0.02
    colorRampBase.color_ramp.elements.new(0.40)  # Add a stop at 0.40
    colorRampBase.color_ramp.elements.new(0.60)  # Add a stop at 0.60
    colorRampBase.color_ramp.elements.new(0.80)  # Add a stop at 0.80
    colorRampBase.color_ramp.elements[0].color = (0, 0, 0, 1)  # Black 0.0
    colorRampBase.color_ramp.elements[1].color = (1, 1, 1, 1)  # White 0.01
    colorRampBase.color_ramp.elements[2].color = (0, 0, 1, 1)  # Blue 0.02
    colorRampBase.color_ramp.elements[3].color = (1, 0, 0, 1)  # Red 0.4
    colorRampBase.color_ramp.elements[4].color = (1, 1, 0, 1)  # Yellow 0.6
    colorRampBase.color_ramp.elements[5].color = (0, 1, 0, 1)  # Green 0.8
    colorRampBase.color_ramp.elements[6].color = (0, 1, 1, 1)  # Cyan 1.0

    attributeEmissionStrength = nodes.new(type="ShaderNodeAttribute")
    attributeEmissionStrength.location = (-400, -300)
    attributeEmissionStrength.attribute_name = "emissionStrength"
    attributeEmissionStrength.attribute_type = 'OBJECT'

    attributeEmissionColor = nodes.new(type="ShaderNodeAttribute")
    attributeEmissionColor.location = (-400, -100)
    attributeEmissionColor.attribute_name = "emissionColor"
    attributeEmissionColor.attribute_type = 'OBJECT'

    colorRampEmission = nodes.new(type="ShaderNodeValToRGB")
    colorRampEmission.location = (-200, -100)
    colorRampEmission.color_ramp.interpolation = 'CARDINAL'  # Ensure linear interpolation
    colorRampEmission.color_ramp.elements.new(0.01)  # Add a stop at 0.01
    colorRampEmission.color_ramp.elements.new(0.02)  # Add a stop at 0.02
    colorRampEmission.color_ramp.elements.new(0.40)  # Add a stop at 0.40
    colorRampEmission.color_ramp.elements.new(0.60)  # Add a stop at 0.60
    colorRampEmission.color_ramp.elements.new(0.80)  # Add a stop at 0.80
    colorRampEmission.color_ramp.elements[0].color = (0, 0, 0, 1)  # Black 0.0
    colorRampEmission.color_ramp.elements[1].color = (1, 1, 1, 1)  # White 0.01
    colorRampEmission.color_ramp.elements[2].color = (0, 0, 1, 1)  # Blue 0.02
    colorRampEmission.color_ramp.elements[3].color = (1, 0, 0, 1)  # Red 0.4
    colorRampEmission.color_ramp.elements[4].color = (1, 1, 0, 1)  # Yellow 0.6
    colorRampEmission.color_ramp.elements[5].color = (0, 1, 0, 1)  # Green 0.8
    colorRampEmission.color_ramp.elements[6].color = (0, 1, 1, 1)  # Cyan 1.0

    attributeAlpha = nodes.new(type="ShaderNodeAttribute")
    attributeAlpha.location = (-400, -500)
    attributeAlpha.attribute_name = "alpha"
    attributeAlpha.attribute_type = 'OBJECT'

    # Connect the nodes
    links.new(attributeBaseColor.outputs["Fac"], colorRampBase.inputs["Fac"])  # Emission color
    links.new(attributeEmissionStrength.outputs["Fac"], principledBSDF.inputs["Emission Strength"])  # Emission strength
    links.new(attributeAlpha.outputs["Fac"], principledBSDF.inputs["Alpha"])  # Emission strength
    links.new(attributeEmissionColor.outputs["Fac"], colorRampEmission.inputs["Fac"])  # Emission color
    links.new(colorRampBase.outputs["Color"], principledBSDF.inputs["Base Color"])  # Base color
    links.new(colorRampEmission.outputs["Color"], principledBSDF.inputs["Emission Color"])  # Emission color
    links.new(principledBSDF.outputs["BSDF"], output.inputs["Surface"])  # Output surface

    return mat

def createCompositorNodes():

    # Enable the compositor
    bScn.use_nodes = True
    nodeTree = bScn.node_tree

    # Remove existing nodes
    for node in nodeTree.nodes:
        nodeTree.nodes.remove(node)

    # Add necessary nodes
    renderLayersNode = nodeTree.nodes.new(type='CompositorNodeRLayers')
    renderLayersNode.location = (0, 0)

    glareNode = nodeTree.nodes.new(type='CompositorNodeGlare')
    glareNode.location = (300, 0)

    # Configure the Glare node
    glareNode.glare_type = 'BLOOM'
    glareNode.quality = 'MEDIUM'
    glareNode.mix = 0.0
    glareNode.threshold = 5
    glareNode.size = 4

    compositeNode = nodeTree.nodes.new(type='CompositorNodeComposite')
    compositeNode.location = (600, 0)

    # Connect the nodes
    links = nodeTree.links
    links.new(renderLayersNode.outputs['Image'], glareNode.inputs['Image'])
    links.new(glareNode.outputs['Image'], compositeNode.inputs['Image'])
    
    return

def viewportShadingRendered():
    # Enable viewport shading in Rendered mode
    for area in bCon.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'RENDERED'

    # Enable compositor (this ensures nodes are active)
    bScn.use_nodes = True

    # Ensure compositor updates are enabled
    bScn.render.use_compositing = True
    bScn.render.use_sequencer = False  # Disable sequencer if not needed
    
    return


def createSparklesCloudGN(nameGN, obj, sparklesMaterial):
    # Ajouter un modificateur Geometry Nodes
    mod = obj.modifiers.new(name=nameGN, type='NODES')
    
    # Créer un nouveau groupe de nœuds Geometry Nodes
    nodeGroup = bDat.node_groups.new(name=nameGN, type="GeometryNodeTree")

    # Associer le groupe au modificateur
    mod.node_group = nodeGroup

    # Définir les entrées et sorties du groupe
    nodeGroup.interface.new_socket(socket_type="NodeSocketGeometry", name="Geometry", in_out="INPUT")
    socketRadiusSparklesCloud = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="radiusSparklesCloud", in_out="INPUT", description="Radius of the sparkles cloud")
    socketRadiusSparkles = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="radiusSparkles", in_out="INPUT", description="Radius of the sparkles")
    socketDensityCloud = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="densityCloud", in_out="INPUT", description="Density of the sparkles cloud")
    socketDensitySeed = nodeGroup.interface.new_socket(socket_type="NodeSocketInt", name="densitySeed", in_out="INPUT", description="Seed of the sparkles cloud")
    nodeGroup.interface.new_socket(socket_type="NodeSocketMaterial", name="sparkleMaterial", in_out="INPUT")
    nodeGroup.interface.new_socket(socket_type="NodeSocketGeometry", name="Geometry", in_out="OUTPUT")

    socketRadiusSparklesCloud.default_value = 1.0
    socketRadiusSparklesCloud.min_value = 0.0
    socketRadiusSparklesCloud.max_value = 1.0
    
    socketRadiusSparkles.default_value = 0.02
    socketRadiusSparkles.min_value = 0.0
    socketRadiusSparkles.max_value = 0.05
    
    socketDensityCloud.default_value = 10
    socketDensityCloud.min_value = 0
    socketDensityCloud.max_value = 10
        
    socketDensitySeed.default_value = 0
    socketDensitySeed.min_value = 0
    socketDensitySeed.max_value = 100000
    
    # Ajouter les nœuds nécessaires
    nodeInput = nodeGroup.nodes.new("NodeGroupInput")
    nodeInput.location = (-500, 0)

    nodeOutput = nodeGroup.nodes.new("NodeGroupOutput")
    nodeOutput.location = (800, 0)

    icoSphereCloud = nodeGroup.nodes.new("GeometryNodeMeshIcoSphere")
    icoSphereCloud.location = (-300, 200)
    icoSphereCloud.inputs["Subdivisions"].default_value = 3

    multiplyNode = nodeGroup.nodes.new("ShaderNodeMath")
    multiplyNode.location = (-300, -100)
    multiplyNode.operation = 'MULTIPLY'
    multiplyNode.inputs[1].default_value = 10.0

    distributePoints = nodeGroup.nodes.new("GeometryNodeDistributePointsOnFaces")
    distributePoints.location = (0, 200)

    icoSphereSparkles = nodeGroup.nodes.new("GeometryNodeMeshIcoSphere")
    icoSphereSparkles.location = (0, -200)
    icoSphereSparkles.inputs["Subdivisions"].default_value = 1

    instanceOnPoints = nodeGroup.nodes.new("GeometryNodeInstanceOnPoints")
    instanceOnPoints.location = (300, 200)

    setMaterial = nodeGroup.nodes.new("GeometryNodeSetMaterial")
    setMaterial.location = (600, 200)
    
    # Connecter les nœuds
    links = nodeGroup.links
    links.new(icoSphereCloud.outputs["Mesh"], distributePoints.inputs["Mesh"])
    links.new(distributePoints.outputs["Points"], instanceOnPoints.inputs["Points"])
    links.new(multiplyNode.outputs["Value"], distributePoints.inputs["Density"])
    links.new(instanceOnPoints.outputs["Instances"], setMaterial.inputs["Geometry"])
    links.new(icoSphereSparkles.outputs["Mesh"], instanceOnPoints.inputs["Instance"])
    links.new(nodeInput.outputs["radiusSparklesCloud"], icoSphereCloud.inputs["Radius"])
    links.new(nodeInput.outputs["radiusSparkles"], icoSphereSparkles.inputs["Radius"])
    links.new(nodeInput.outputs["densityCloud"], multiplyNode.inputs[0])
    links.new(nodeInput.outputs["densitySeed"], distributePoints.inputs["Seed"])
    links.new(nodeInput.outputs["sparkleMaterial"], setMaterial.inputs["Material"])
    links.new(setMaterial.outputs["Geometry"], nodeOutput.inputs["Geometry"])

    wLog(f"Geometry Nodes '{nameGN}' created successfully!")
    return

# Retrieve location at frame from any Object
def getObjPositionAtFrame(obj, frame):
    # Save current frame
    # currentFrame = bCon.scene.frame_current
    # Go to frame specified
    bCon.scene.frame_set(int(frame))
    # Force update scene
    bCon.view_layer.update()
    # Get worldPos of obj
    worldPos = obj.matrix_world.translation.copy()
    # Restore saved frame
    # bCon.scene.frame_set(currentFrame)
    return worldPos

# Retrieve octave and noteNumber from note
def extractOctaveAndNote(note):
    octave = note // 12
    noteNumber = note % 12
    return octave, noteNumber

"""
Blender visualisation one BarGraph by track
"""
def createBlenderBGAnimation(masterCollection, trackMask, typeAnim):
    # noteMidRange is a global variable

    wLog("Create a BarGraph Animation type="+typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, numberOfRenderedTracks = parseRangeFromTracks(trackMask)

    # Create master BG collection
    BGCollect = create_collection("BarGraph", masterCollection)

    # Create model Cubes
    BGModelCube = addCube(hiddenCollection, "BGModelCube", matGlobalCustom, False, (0, 0, -5), (1,1,1))

    # Create cubes from track
    # Parse track to create BG
    trackCenter = numberOfRenderedTracks / 2
    cubeSpace = BGModelCube.scale.x * 1.2 # mean x size of cube + 20 %

    trackCount = 0
    # Parse track to create BG
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue
        # create collection
        BGTrackName = "BG-"+str(trackIndex)+"-"+track.name
        BGTrackCollect = create_collection(BGTrackName, BGCollect)
        trackCount += 1

        # one cube per note used
        for note in track.notesUsed:
            # create cube
            cubeName = "Cube-"+str(trackIndex)+"-"+str(note)
            offsetX = (note - noteMidRange) * cubeSpace
            offsetY = (trackIndex - trackCenter) * cubeSpace + cubeSpace / 2
            cubeLinked = createDuplicateLinkedObject(BGTrackCollect, BGModelCube, cubeName)
            cubeLinked.location = (offsetX, offsetY, 0)
            cubeLinked["baseColor"] = colorFromNoteNumber(note % 12)
                
        wLog("BarGraph - create "+str(len(track.notesUsed))+" cubes for track "+ str(trackIndex) +" (range noteMin-noteMax) ("+str(track.minNote)+"-"+str(track.maxNote)+")")

    # Create a plane by octave to have a visualisation for them
    # minnote and maxnote are usefull to know the range of octave
    minOctave = noteMin // 12
    maxOctave = noteMax // 12
    
    planPosXOffset = (((noteMidRange % 12) - 5) * cubeSpace) - (cubeSpace / 2)
    for octave in range(minOctave, maxOctave + 1):
        planSizeX = 12 * cubeSpace
        planSizeY = trackCount * cubeSpace
        planPosX = (octave - (noteMidRange // 12)) * 12 * cubeSpace
        planPosX -= planPosXOffset
        obj = createRectangularPlane(BGCollect, "BGPlane-"+str(octave), matGlobalCustom, planSizeX, planSizeY, (planPosX, 0, (-BGModelCube.scale.z / 2)*1.05))
        if octave % 2 == 0:
            obj["baseColor"] = 0.6 # Yellow
        else: 
            obj["baseColor"] = 1.0 # Cyan

    # Animate cubes accordingly to notes event
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, numberOfRenderedTracks)

        for currentIndex, note in enumerate(track.notes):
            # Find the previous note with the same note number
            previousNote = None
            for prevIndex in range(currentIndex - 1, -1, -1):
                if track.notes[prevIndex].noteNumber == note.noteNumber:
                    previousNote = track.notes[prevIndex]
                    break

            # Find the next note with the same note number
            nextNote = None
            for nextIndex in range(currentIndex + 1, len(track.notes)):
                if track.notes[nextIndex].noteNumber == note.noteNumber:
                    nextNote = track.notes[nextIndex]
                    break

            # Construct the cube name and animate
            cubeName = "Cube-" + str(trackIndex) + "-" + str(note.noteNumber)
            noteObj = bDat.objects[cubeName]
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote, colorTrack)

        wLog("BarGraph - Animate cubes for track " +str(trackIndex)+" (notesCount) ("+str(len(track.notes))+")")

"""
End of BG visualisation
"""

import re

"""
Blender visualisation with barrel organ

    Strip simulation for piano, note 21 (A0) to 128 (C8) => 88 notes
    A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C
    0   1             2             3             4             5             6             7             8
    0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    
    X for note height
    Y for note length

"""
def createStripNotes(masterCollection, trackMask, typeAnim):

    wLog("Create a Strip Notes Animation type="+typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, trackProcessed = parseRangeFromTracks(trackMask)

    stripModelCube = addCube(hiddenCollection, "StripNotesModelCube", matGlobalCustom, False, (0, 0, -5), (1,1,1))
    stripCollect = create_collection("StripNotes", masterCollection)

    # Evaluate the real count of track processed
    # For all tracks processed : 
    # - length in sec
    length = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue
        length = max(length, track.notes[-1].timeOff)

    notecount = (noteMax - noteMin) + 1
    noteMiddle = noteMin + math.ceil(notecount / 2)

    marginExtX = 0 # in ?
    marginExtY = 0 # in sec
    cellSizeX = 1 # size X for each note in centimeters
    cellSizeY = 4 # size for each second in centimeters
    intervalX = cellSizeX / 10
    intervalTracks = (cellSizeX + intervalX) * (trackProcessed - 1)
    planSizeX = (marginExtX * 2) + (notecount * cellSizeX) + (notecount * intervalTracks)
    planSizeY = (length + (marginExtY *2)) * cellSizeY

    # Parse tracks
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        offSetX = (trackIndex * (cellSizeX + intervalX))
        intervalY = 0 # have something else to 0 create artefact in Y depending on how many note
        
        # Create collections
        notesCollection = create_collection("Notes-Track-"+str(trackIndex), stripCollect)

        sizeX = cellSizeX

        colorTrack = colorFromIndex(trackIndex, trackProcessed)

        for noteIndex, note in enumerate(track.notes):
            posX = ((note.noteNumber - noteMiddle) * (cellSizeX + intervalTracks)) + offSetX + (sizeX / 2)
            sizeY = round(((note.timeOff - note.timeOn) * cellSizeY),2)
            posY = ((marginExtY + note.timeOn) * (cellSizeY + intervalY)) + (sizeY / 2)
            nameOfNotePlayed = "Note-"+str(trackIndex)+"-"+str(noteIndex)

            # Duplicate the existing note
            noteObj = createDuplicateLinkedObject(notesCollection, stripModelCube, nameOfNotePlayed)
            noteObj.location = (posX, posY, 0) # Set instance position
            noteObj.scale = (sizeX, sizeY, 1) # Set instance scale
            noteObj["baseColor"] = colorTrack

            # Find the previous note with the same note number
            previousNote = None
            for prevIndex in range(noteIndex - 1, -1, -1):
                if track.notes[prevIndex].noteNumber == note.noteNumber:
                    previousNote = track.notes[prevIndex]
                    break

            # Find the next note with the same note number
            nextNote = None
            for nextIndex in range(noteIndex + 1, len(track.notes)):
                if track.notes[nextIndex].noteNumber == note.noteNumber:
                    nextNote = track.notes[nextIndex]
                    break

            # Animate note
            # Be aware to animate duplicate only, never the model one
            # Pass the current note, previous note, and next note to the function
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote, colorTrack)
           
            
        wLog("Notes Strip track "+str(trackIndex)+" - create & animate "+ str(noteIndex + 1))

    obj = createRectangularPlane(stripCollect, "NotesStripPlane", matGlobalCustom, planSizeX, planSizeY, (0, planSizeY / 2, (-stripModelCube.scale.z / 2)*1.05))
    obj["baseColor"] = 0.01 # White

    return obj

"""
Blender visualisation with waterfall on note strip
"""
def createWaterFall(masterCollection, trackMask, typeAnim):
    
    wLog("Create a waterfall Notes Animation type")

    createStripNotes(masterCollection, trackMask, typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Initialize a list to store all notes from the selected tracks along with their track index
    selectedNotes = []

    # Iterate through all tracks and collect notes from the selected tracks
    for trackIndex, track in enumerate(tracks):
        if trackIndex in listOfSelectedTrack:  # Check if the current track is selected
            # Add each note as a tuple (trackIndex, note) to the list
            selectedNotes.extend((trackIndex, note) for note in track.notes)

    # Find the tuple with the note that has the smallest timeOn value
    noteMinTimeOn = min(selectedNotes, key=lambda x: x[1].timeOn)
    # Find the tuple with the note that has the largest timeOff value
    noteMaxTimeOff = max(selectedNotes, key=lambda x: x[1].timeOff)

    # Get first and last note object
    noteIndex = tracks[noteMinTimeOn[0]].notes.index(noteMinTimeOn[1])
    FirstNotePlayed = "Note-"+str(noteMinTimeOn[0])+"-"+str(noteIndex)
    noteIndex = tracks[noteMaxTimeOff[0]].notes.index(noteMaxTimeOff[1])
    LastNotePlayed = "Note-"+str(noteMaxTimeOff[0])+"-"+str(noteIndex)
    firstNote = bDat.objects[FirstNotePlayed]
    lastNote = bDat.objects[LastNotePlayed]

    # Create a new camera
    cameraData = bDat.cameras.new(name="Camera")
    cameraObj = bDat.objects.new("Camera", cameraData)
    masterCollection.objects.link(cameraObj)

    # orthographic mode
    cameraData.type = 'ORTHO'

    objStripePlan = bDat.objects["NotesStripPlane"]
    sizeX = objStripePlan.scale.x

    # othographic scale (Field of View)
    cameraData.ortho_scale = sizeX # 90

    offSetYCamera = sizeX*(9/16)/2
    orthoFOV = 38.6

    CameraLocationZ = (sizeX/2) / (math.tan(orthoFOV/2))
    
    # Set the initial position of the camera
    cameraObj.location = (0, offSetYCamera, CameraLocationZ)  # X, Y, Z
    cameraObj.rotation_euler = (0, 0, 0)  # Orientation
    cameraObj.data.shift_y = -0.01

    # Add a keyframe for the starting Y position
    cameraObj.location.y = offSetYCamera + firstNote.location.y - (firstNote.scale.y/2)
    cameraObj.keyframe_insert(data_path="location", index=1, frame=noteMinTimeOn[1].timeOn*fps)

    # Add a keyframe for the starting Y position
    cameraObj.location.y = offSetYCamera + lastNote.location.y + (lastNote.scale.y/2)
    cameraObj.keyframe_insert(data_path="location", index=1, frame=noteMaxTimeOff[1].timeOff*fps)

    # Set the active camera for the scene
    bScn.camera = cameraObj

    # Rendre l'animation linéaire
    action = cameraObj.animation_data.action  # Récupérer l'action d'animation de l'objet
    fcurve = action.fcurves.find(data_path="location", index=1)  # F-Curve pour l'axe Y

    if fcurve:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'  # Définir l'interpolation sur 'LINEAR'

"""
Blender visualisation with fireworks
Axe X for note in octave
Axe Y octave
Axe Z for velocity
Note length for spread
Color = Tracks

V1 with sphere
V2 with trajectory
"""
def createFireworksV1(masterCollection, trackMask, typeAnim):

    wLog("Create a Fireworks V1 Notes Animation type="+typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create master BG collection
    FWCollect = create_collection("FireworksV1", masterCollection)

    # Create model Sphere
    FWModelSphere = addIcoSphere(hiddenCollection, "BGModelCube", matGlobalCustom, (0, 0, -5), 1)

    # create sparklesCloudGN and set parameters
    createSparklesCloudGN("SparklesCloud", FWModelSphere, matGlobalCustom)
    radiusSparklesCloud = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["radiusSparklesCloud"].identifier
    FWModelSphere.modifiers["SparklesCloud"][radiusSparklesCloud] = 1.0
    radiusSparkles = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["radiusSparkles"].identifier
    FWModelSphere.modifiers["SparklesCloud"][radiusSparkles] = 0.02
    densityCloud = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["densityCloud"].identifier
    FWModelSphere.modifiers["SparklesCloud"][densityCloud] = 0.1
    sparkleMaterial = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["sparkleMaterial"].identifier
    FWModelSphere.modifiers["SparklesCloud"][sparkleMaterial] = matGlobalCustom
       
    spaceX = 5
    spaceY = 5
    offsetX = 5.5 * spaceX # center of the octave, mean between fifth and sixt note
    offsetY = (octaveCount * spaceY) - (spaceY / 2)

    # Construction
    noteCount = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, len(tracks))

        # create collection
        FWTrackName = "FW-"+str(trackIndex)+"-"+track.name
        FWTrackCollect = create_collection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            noteCount += 1
            # create sphere
            sphereName = "Sphere-"+str(trackIndex)+"-"+str(note)
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelSphere, sphereName)
            sphereLinked.location = ((note % 12) * spaceX - offsetX, (note // 12) * spaceY - offsetY, 0)
            sphereLinked.scale = (0,0,0)
            sphereLinked["baseColor"] = colorTrack
            sphereLinked["emissionColor"] = colorTrack
            sparkleCloudSeed = sphereLinked.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
            sphereLinked.modifiers["SparklesCloud"][sparkleCloudSeed] = noteCount

        wLog("Fireworks - create "+str(len(track.notesUsed))+" sparkles cloud for track "+ str(trackIndex) +" (range noteMin-noteMax) ("+str(track.minNote)+"-"+str(track.maxNote)+")")

    # Animation
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, len(tracks))

        for currentIndex, note in enumerate(track.notes):
            # Find the previous note with the same note number
            previousNote = None
            for prevIndex in range(currentIndex - 1, -1, -1):
                if track.notes[prevIndex].noteNumber == note.noteNumber:
                    previousNote = track.notes[prevIndex]
                    break

            # Find the next note with the same note number
            nextNote = None
            for nextIndex in range(currentIndex + 1, len(track.notes)):
                if track.notes[nextIndex].noteNumber == note.noteNumber:
                    nextNote = track.notes[nextIndex]
                    break

            # Construct the sphere name and animate
            cubeName = "Sphere-" + str(trackIndex) + "-" + str(note.noteNumber)
            noteObj = bDat.objects[cubeName]
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote, colorTrack)

        wLog("Fireworks - Animate sparkle clouds for track " +str(trackIndex)+" (notesCount) ("+str(len(track.notes))+")")

    return


"""
Blender visualisation with fireworks
Axe X for note in octave
Axe Y octave
Axe Z for velocity
Note length for spread
Color = Tracks

V1 with sphere
V2 with trajectory
"""
def createFireworksV2(masterCollection, trackMask, typeAnim):

    wLog("Create a Fireworks V2 Notes Animation type="+typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create master BG collection
    FWCollect = create_collection("FireworksV2", masterCollection)

    # Create model objects
    FWModelEmitter = addIcoSphere(hiddenCollection, "FWV2Emitter", matGlobalCustom, (0, 0, -5), 1)
    FWModelSparkle = addIcoSphere(hiddenCollection, "FWV2Sparkles", matGlobalCustom, (0, 0, -5), 0.1)

    spaceX = 5
    spaceY = 5
    spaceZ = 5
    offsetX = 5.5 * spaceX # center of the octave, mean between fifth and sixt note
    octaveMin = noteMin // 12
    octaveMax = noteMax // 12
    octaveCenter = ((octaveMax - octaveMin) / 2) + octaveMin
    trackCenter = (len(tracks)-1) / 2

    # Construction
    noteCount = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = (trackIndex + 1) / (len(tracks) + 1) # color for track
        colorTrack = (int(colorTrack * 255) ^ 0xAA) /255 # XOR operation to get a different color

        # create collection
        FWTrackName = "FW-"+str(trackIndex)+"-"+track.name
        FWTrackCollect = create_collection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            # create sphere
            pX = (note % 12) * spaceX - offsetX
            pY = ((note // 12) - octaveCenter) * spaceY
            pZ = (trackIndex - trackCenter) * spaceZ
            emitterName = "noteEmitter-"+str(trackIndex)+"-"+str(note)
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelEmitter, emitterName)
            sphereLinked.location = (pX, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["alpha"] = 0.0
            sparkleName = "noteSparkles-"+str(trackIndex)+"-"+str(note)
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelSparkle, sparkleName)
            sphereLinked.location = (pX + 1000, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["baseColor"] = colorTrack
            sphereLinked["emissionColor"] = colorTrack

        wLog("Fireworks V2 - create "+str(len(track.notesUsed))+" sparkles cloud for track "+ str(trackIndex) +" (range noteMin-noteMax) ("+str(track.minNote)+"-"+str(track.maxNote)+")")

        # create animation
        noteCount = 0
        for currentIndex, note in enumerate(track.notes):
            noteCount += 1
            
            frameTimeOn = int(note.timeOn * fps)
            frameTimeOff = int(note.timeOff * fps)

            emitterName = "noteEmitter-"+str(trackIndex)+"-"+str(note.noteNumber)
            emitterObj = bDat.objects[emitterName]

            # Add a particle system to the object
            psName = "PS-" + str(noteCount)
            particleSystem = emitterObj.modifiers.new(name=psName, type='PARTICLE_SYSTEM')
            particleSettings = bpy.data.particles.new(name="ParticleSettings")

            # Assign the particle settings to the particle system
            particleSystem.particle_system.settings = particleSettings

            # Configure particle system settings
            particleSettings.count = 100  # Number of particles
            particleSettings.lifetime = 50  # Lifetime of each particle
            particleSettings.frame_start = frameTimeOn  # Start frame for particle emission
            particleSettings.frame_end = frameTimeOff  # End frame for particle emission
            particleSettings.normal_factor = note.velocity  # Speed of particles along normals
            particleSettings.effector_weights.gravity = 0.1  # Reduce gravity influence to 20%

            # Set the particle system to render the sparkle object
            Brigthness = 4 + (note.velocity * 10)
            particleSettings.render_type = 'OBJECT'
            sparkleName = "noteSparkles-"+str(trackIndex)+"-"+str(note.noteNumber)
            sparkleObj = bDat.objects[sparkleName]
            sparkleObj["emissionStrength"] = Brigthness

            particleSettings.instance_object = sparkleObj
            particleSettings.particle_size = 1.0  # Size of particles
            particleSettings.size_random = 0.2    # 20 % of variability

            # sparkleObj.scale = (1,1,1)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOn)

            # sparkleObj.scale = (0,0,0)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOff)

        wLog("Fireworks V2 - animate "+str(noteCount)+" sparkles cloud for track "+ str(trackIndex))

    # Animation

    return

def createFountain(masterCollection, trackMask, typeAnim):

    wLog("Create a Fountain Animation type=" + typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create Collection
    fountainCollection = create_collection("Fountain", masterCollection)

    # Create model objects
    fountainModelPlane = createRectangularPlane(hiddenCollection, "fountainModelPlane", matGlobalCustom, 1, 1, (0, 0, -10))
    # fountainModelParticle = addIcoSphere(hiddenCollection, "fountainModelParticle", matGlobalCustom, (0, 0, -5), 1)
    fountainModelParticle = addCube(hiddenCollection, "fountainModelParticle", matGlobalCustom, False, (2, 0, -10), (1,1,1))
    fountainModelEmitter = addCylinder(hiddenCollection, "fountainModelEmitter", matGlobalCustom, (4, 0, -10), 1, 1)

    # Construction of the fountain Targets
    theta = math.radians(360)  # 2 Pi, just one circle
    alpha = theta / 12  # 12 is the Number of notes per octave
    for note in range(132):
        octave, numNote = extractOctaveAndNote(note)
        targetName = "Target-" + str(numNote) + "-" + str(octave)
        targetObj = createDuplicateLinkedObject(fountainCollection, fountainModelPlane, targetName)
        spaceY = 0.1
        spaceX = 0.1
        angle = (12 - note) * alpha
        distance = (octave * (1 + spaceX)) + 4
        pX = (distance * math.cos(angle))
        pY = (distance * math.sin(angle))
        rot = math.radians(math.degrees(angle))
        targetObj.location = (pX, pY, 0)
        targetObj.rotation_euler = (0, 0, rot)
        sX = 1 # mean size of note in direction from center to border (octave)
        sY = (2 * distance * math.tan(math.radians(15))) - spaceY # mean size of note in rotate direction (numNote)
        targetObj.scale = (sX, sY, 1)
        targetObj["baseColor"] = colorFromNoteNumber(numNote)
        # Add Taper modifier
        simpleDeformModifier = targetObj.modifiers.new(name="SimpleDeform", type='SIMPLE_DEFORM')
        simpleDeformModifier.deform_method = 'TAPER'
        bigSide = (2 * (distance+sX/2) * math.tan(math.radians(15))) - spaceY
        taperFactor = 2*(bigSide/sY-1)
        simpleDeformModifier.factor = taperFactor
        # Add collision Physics
        targetObj.modifiers.new(name="Collision", type='COLLISION')  

    wLog("Fountain - create 132 targets")

    # Create circle curve for trajectory of emitters
    fountainEmitterTrajectory = addBezierCircle(hiddenCollection, "fountainEmitterTrajectory")
    fountainEmitterTrajectory.location = (0, 0, 3)
    fountainEmitterTrajectory.scale = (20, 20, 20)

    # Add rotation animation
    rotationSpeed = 0.05  # Rotations per second
    startFrame = 1
    endFrame = int(lastNoteTimeOff * fps)  # Use global lastNoteTimeOff
    totalRotations = rotationSpeed * lastNoteTimeOff

    # Set keyframes for Z rotation
    fountainEmitterTrajectory.rotation_euler.z = 0
    fountainEmitterTrajectory.keyframe_insert(data_path="rotation_euler", index=2, frame=startFrame)

    fountainEmitterTrajectory.rotation_euler.z = totalRotations * 2 * math.pi  # Convert to radians
    fountainEmitterTrajectory.keyframe_insert(data_path="rotation_euler", index=2, frame=endFrame)

    # Make animation linear
    for fcurve in fountainEmitterTrajectory.animation_data.action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'

    g = -bScn.gravity[2]  # z gravity from blender (m/s^2)

    delayImpact = 3.0  # Time in second from emitter to target
    frameDelayImpact = delayImpact * fps

    # Create empty object for storing somes constants for drivers
    fountainConstantsObj = bDat.objects.new("fountainConstantsValues", None)
    fountainConstantsObj.location=(6,0,-10)
    hiddenCollection.objects.link(fountainConstantsObj)
    fountainConstantsObj["delay"] = delayImpact

    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, len(tracks))

        # Particle
        particleName = "Particle-" + str(trackIndex) + "-" + track.name
        particleObj = createDuplicateLinkedObject(hiddenCollection, fountainModelParticle, particleName)
        particleObj.name = particleName
        particleObj.location = (trackIndex * 2, 0, -12)
        particleObj.scale = (0.3,0.3,0.3)
        particleObj["baseColor"] = colorTrack
        particleObj["emissionColor"] = colorTrack
        particleObj["emissionStrength"] = 8.0

        # Emitter around the targets
        emitterName = "Emitter-" + str(trackIndex) + "-" + track.name
        emitterObj = createDuplicateLinkedObject(fountainCollection, fountainModelEmitter, emitterName)

        # Add Clamp To constraint
        clampConstraint = emitterObj.constraints.new(type='CLAMP_TO')
        clampConstraint.target = fountainEmitterTrajectory
        clampConstraint.use_cyclic = True  # Enable cyclic for closed curve

        # Calculate position on curve (0 to 1)
        curvePosition = trackIndex / tacksProcessed
        clampConstraint.target_space = 'LOCAL'

        emitterObj.location = (4 * curvePosition, 0, 0) # *4 ?
        emitterObj.scale = (1, 1, 0.2)
        emitterObj["baseColor"] = colorTrack
        emitterObj["emissionColor"] = colorTrack

        # Set initial position on curve
        clampConstraint.main_axis = 'CLAMPTO_X'  # Use X axis for clamping

        # One particle per note
        for currentIndex, note in enumerate(track.notes):

            frameTimeOn = int(note.timeOn * fps)
            frameTimeOff = int(note.timeOff * fps)
            octave, numNote = extractOctaveAndNote(note.noteNumber)

            # Add a particle system to the object
            pSystemName = "ParticleSystem-" + str(octave)+"-"+str(currentIndex)
            particleSystem = emitterObj.modifiers.new(name=pSystemName, type='PARTICLE_SYSTEM')
            pSettingName = "ParticleSettings-" + str(octave)+"-"+str(currentIndex)
            particleSettings = bDat.particles.new(name=pSettingName)
            particleSystem.particle_system.settings = particleSettings

            # Configure particle system settings - Emission
            particleSettings.count = 1
            particleSettings.lifetime = fps * 4
            # Be sure to initialize frame_end before frame_start because
            # frame_start can't be greather than frame_end at any time
            # particleSettings.frame_end = frameTimeOff - frameDelayImpact
            particleSettings.frame_end = frameTimeOn - frameDelayImpact + 1
            particleSettings.frame_start = frameTimeOn - frameDelayImpact

            # Configure particle system settings - Emission - Source
            particleSettings.emit_from = 'FACE'
            particleSettings.distribution = 'GRID'
            particleSettings.grid_resolution = 1
            particleSettings.grid_random = 0

            # Configure particle system settings - Velocity - Using drivers
            # Retrieve Target Object
            targetName = "Target-" + str(numNote) + "-" + str(octave)
            target = bDat.objects[targetName]

            # Add drivers for object_align_factors
            for i, axis in enumerate(['X', 'Y', 'Z']):
                driver = particleSettings.driver_add('object_align_factor', i).driver
                driver.type = 'SCRIPTED'
                
                # Add variables for emitter position
                varE = driver.variables.new()
                varE.name = f"e{axis}"
                varE.type = 'TRANSFORMS'
                varE.targets[0].id = emitterObj
                varE.targets[0].transform_type = f'LOC_{axis}'
                varE.targets[0].transform_space = 'WORLD_SPACE'
                
                # Add variables for target position
                varT = driver.variables.new()
                varT.name = f"t{axis}"
                varT.type = 'TRANSFORMS'
                varT.targets[0].id = target
                varT.targets[0].transform_type = f'LOC_{axis}'
                varT.targets[0].transform_space = 'WORLD_SPACE'
                
                # Add delay variable (from emitter object)
                varDelay = driver.variables.new()
                varDelay.name = "delay" 
                varDelay.type = 'SINGLE_PROP'
                varDelay.targets[0].id = fountainConstantsObj
                varDelay.targets[0].data_path = '["delay"]'

                if axis == 'Z':
                    # driver.expression = f"(t{axis} - e{axis} - 0.5 * g * delay**2) / delay" # initiale expression
                    driver.expression = f"(t{axis} - e{axis} + 4.905 * delay*delay) / delay" # Optimized expression to avoid "Slow Python Expression"
                else:
                    driver.expression = f"(t{axis} - e{axis}) / delay"

            # Configure particle system settings - Render
            particleSettings.render_type = 'OBJECT'
            particleSettings.instance_object = particleObj
            particleSettings.particle_size = 0.7  # Base size of the particle

            # Configure particle system settings - Fields Weights
            particleSettings.effector_weights.gravity = 1

        wLog("Fountain - create "+str(currentIndex)+" particles for track "+ str(trackIndex))

    # Animation of target notes
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, len(tracks))

        for currentIndex, note in enumerate(track.notes):
            # Find the previous note with the same note number
            previousNote = None
            for prevIndex in range(currentIndex - 1, -1, -1):
                if track.notes[prevIndex].noteNumber == note.noteNumber:
                    previousNote = track.notes[prevIndex]
                    break

            # Find the next note with the same note number
            nextNote = None
            for nextIndex in range(currentIndex + 1, len(track.notes)):
                if track.notes[nextIndex].noteNumber == note.noteNumber:
                    nextNote = track.notes[nextIndex]
                    break

            # Construct the sphere name and animate
            octave, numNote = extractOctaveAndNote(note.noteNumber)
            targetName = "Target-" + str(numNote) + "-" + str(octave)
            noteObj = bDat.objects[targetName]
            noteAnimate(noteObj, "MultiLight", note, previousNote, nextNote, colorTrack)

        wLog("Fountain - animate targets for track "+ str(trackIndex))

    return

"""
Main
"""

# To convert easily from midi notation to name of note
# C4 is median DO on piano keyboard and is notated 60
numNoteToAlpha = {
 0:   "C",   1: "C#",   2: "D",   3: "D#",   4: "E",   5: "F",   6: "F#",   7: "G",   8: "G#",   9: "A",  10: "A#",  11: "B",
 12:  "C",  13: "C#",  14: "D",  15: "D#",  16: "E",  17: "F",  18: "F#",  19: "G",  20: "G#",  21: "A",  22: "A#",  23: "B",
 24:  "C",  25: "C#",  26: "D",  27: "D#",  28: "E",  29: "F",  30: "F#",  31: "G",  32: "G#",  33: "A",  34: "A#",  35: "B",
 36:  "C",  37: "C#",  38: "D",  39: "D#",  40: "E",  41: "F",  42: "F#",  43: "G",  44: "G#",  45: "A",  46: "A#",  47: "B",
 48:  "C",  49: "C#",  50: "D",  51: "D#",  52: "E",  53: "F",  54: "F#",  55: "G",  56: "G#",  57: "A",  58: "A#",  59: "B",
 60:  "C",  61: "C#",  62: "D",  63: "D#",  64: "E",  65: "F",  66: "F#",  67: "G",  68: "G#",  69: "A",  70: "A#",  71: "B",
 72:  "C",  73: "C#",  74: "D",  75: "D#",  76: "E",  77: "F",  78: "F#",  79: "G",  80: "G#",  81: "A",  82: "A#",  83: "B",
 84:  "C",  85: "C#",  86: "D",  87: "D#",  88: "E",  89: "F",  90: "F#",  91: "G",  92: "G#",  93: "A",  94: "A#",  95: "B",
 96:  "C",  97: "C#",  98: "D",  99: "D#", 100: "E", 101: "F", 102: "F#", 103: "G", 104: "G#", 105: "A", 106: "A#", 107: "B",
 108: "C", 109: "C#", 110: "D", 111: "D#", 112: "E", 113: "F", 114: "F#", 115: "G", 116: "G#", 117: "A", 118: "A#", 119: "B",
 120: "C", 121: "C#", 122: "D", 123: "D#", 124: "E", 125: "F", 126: "F#", 127: "G"
}

# To convert easily from midi notation to octave of note
# 11 octaves are between 0 and 10
# Not used for now
numNoteToOctave = {
 0:   0,    1: 0,    2: 0,    3: 0,    4: 0,    5: 0,    6: 0,    7: 0,   8: 0,   9: 0,  10: 0,  11: 0,
 12:  1,   13: 1,   14: 1,   15: 1,   16: 1,   17: 1,   18: 1,   19: 1,  20: 1,  21: 1,  22: 1,  23: 1,
 24:  2,   25: 2,   26: 2,   27: 2,   28: 2,   29: 2,   30: 2,   31: 2,  32: 2,  33: 2,  34: 2,  35: 2,
 36:  3,   37: 3,   38: 3,   39: 3,   40: 3,   41: 3,   42: 3,   43: 3,  44: 3,  45: 3,  46: 3,  47: 3,
 48:  4,   49: 4,   50: 4,   51: 4,   52: 4,   53: 4,   54: 4,   55: 4,  56: 4,  57: 4,  58: 4,  59: 4,
 60:  5,   61: 5,   62: 5,   63: 5,   64: 5,   65: 5,   66: 5,   67: 5,  68: 5,  69: 5,  70: 5,  71: 5,
 72:  6,   73: 6,   74: 6,   75: 6,   76: 6,   77: 6,   78: 6,   79: 6,  80: 6,  81: 6,  82: 6,  83: 6,
 84:  7,   85: 7,   86: 7,   87: 7,   88: 7,   89: 7,   90: 7,   91: 7,  92: 7,  93: 7,  94: 7,  95: 7,
 96:  8,   97: 8,   98: 8,   99: 8,  100: 8,  101: 8,  102: 8,  103: 8, 104: 8, 105: 8, 106: 8, 107: 8,
 108: 9,  109: 9,  110: 9,  111: 9,  112: 9,  113: 9,  114: 9,  115: 9, 116: 9, 117: 9, 118: 9, 119: 9,
 120: 10, 121: 10, 122: 10, 123: 10, 124: 10, 125: 10, 126: 10, 127: 10
}

# To convert easily from midi notation to number of note in octave
# Not used for now
numNoteToNumInOctave = {
 0:   0,   1: 1,   2: 2,   3: 3,   4: 4,   5: 5,   6: 6,   7: 7,   8: 8,   9: 9,  10: 10,  11: 11,
 12:  0,  13: 1,  14: 2,  15: 3,  16: 4,  17: 5,  18: 6,  19: 7,  20: 8,  21: 9,  22: 10,  23: 11,
 24:  0,  25: 1,  26: 2,  27: 3,  28: 4,  29: 5,  30: 6,  31: 7,  32: 8,  33: 9,  34: 10,  35: 11,
 36:  0,  37: 1,  38: 2,  39: 3,  40: 4,  41: 5,  42: 6,  43: 7,  44: 8,  45: 9,  46: 10,  47: 11,
 48:  0,  49: 1,  50: 2,  51: 3,  52: 4,  53: 5,  54: 6,  55: 7,  56: 8,  57: 9,  58: 10,  59: 11,
 60:  0,  61: 1,  62: 2,  63: 3,  64: 4,  65: 5,  66: 6,  67: 7,  68: 8,  69: 9,  70: 10,  71: 11,
 72:  0,  73: 1,  74: 2,  75: 3,  76: 4,  77: 5,  78: 6,  79: 7,  80: 8,  81: 9,  82: 10,  83: 11,
 84:  0,  85: 1,  86: 2,  87: 3,  88: 4,  89: 5,  90: 6,  91: 7,  92: 8,  93: 9,  94: 10,  95: 11,
 96:  0,  97: 1,  98: 2,  99: 3, 100: 4, 101: 5, 102: 6, 103: 7, 104: 8, 105: 9, 106: 10, 107: 11,
 108: 0, 109: 1, 110: 2, 111: 3, 112: 4, 113: 5, 114: 6, 115: 7, 116: 8, 117: 9, 118: 10, 119: 11,
 120: 0, 121: 1, 122: 2, 123: 3, 124: 4, 125: 5, 126: 6, 127: 7
}

timeStart = time.time()

# path and name of midi file and so on - temporary => replaced when this become an Blender Extension
path = "W:\\MIDI\\Samples"
# filename = "MIDI Sample"
# filename = "MIDI Sample C3toC4"
# filename = "pianoTest"
# filename = "sampleFountain"
# filename = "T1_CDL" # midifile 1
# filename = "Albinoni"
# filename = "RushE"
# filename = "MIDI-Testing"
# filename = "49f692270904997536e8f5c1070ac880" # Midifile 1 - Multi tracks classical
# filename = "PianoClassique3Tracks978Mesures"
# filename = "ManyTracks" # Midifile 1 - 28 tracks
# filename = "067dffc37b3770b4f1c246cc7023b64d" # One channel Biggest 35188 notes
filename = "a4727cd831e7aff3df843a3da83e8968" # Midifile 0 -  1 track with several channels
# filename = "4cd07d39c89de0f2a3c7b2920a0e0010" # Midifile 0 - 1 track with several channels

pathMidiFile = path + "\\" + filename + ".mid"
pathAudioFile = path + "\\" + filename + ".mp3"
pathLogFile = path + "\\" + filename + ".log"

# Open log file for append
flog = open(pathLogFile, "w+")

wLog("Python version = "+str(sys.version))

# Hope to have 50 fps at min
fps = bScn.render.fps
if fps > 49:
    wLog("FPS is good = "+str(fps))
else:
    wLog("Warning, FPS is too low = "+str(fps))

# Import midi Datas
midiFile, TempoMap, tracks = readMIDIFile(pathMidiFile)

wLog("Midi file path = "+pathMidiFile)
wLog("Midi type = "+str(midiFile.midiFormat))
wLog("PPQN = "+str(midiFile.ppqn))
wLog("Number of tracks = "+str(len(tracks)))

# generate a track count list of dispatched colors
trackColors = generateHSVColors(len(tracks))

# load audio file mp3 with the same name of midi file if exist
# into sequencer
if os.path.exists(pathAudioFile):
    if not bScn.sequence_editor:
        bScn.sequence_editor_create()

    # Clear the VSE, then add an audio file
    bScn.sequence_editor_clear()
    my_contextmem = bCon.area.type
    my_context = 'SEQUENCE_EDITOR'
    bCon.area.type = my_context
    my_context = bCon.area.type
    bOps.sequencer.sound_strip_add(filepath=pathAudioFile, relative_path=True, frame_start=1, channel=1)
    bCon.area.type = my_contextmem
    my_context = bCon.area.type
    bScn.sequence_editor.sequences_all[filename + ".mp3"].volume = 0.25
    wLog("Audio file mp3 is loaded into VSE")
else:
    wLog("Audio file mp3 not exist")

"""
Create (tracks number) lines of (min/max notes) Cubes
"""

# Determine min and max global for centering objects
noteMaxAllTracks = 0
noteMinAllTracks = 1000
firstNoteTimeOn = 1000
lastNoteTimeOff = 0
for track in tracks:
    noteMinAllTracks = min( noteMinAllTracks, track.minNote)
    noteMaxAllTracks = max( noteMaxAllTracks, track.maxNote)
    firstNoteTimeOn = min(firstNoteTimeOn, track.notes[0].timeOn)
    lastNoteTimeOff = max(lastNoteTimeOff, track.notes[-1].timeOff)

noteMidRange = noteMinAllTracks + (noteMaxAllTracks - noteMinAllTracks) / 2
wLog("note min =  " + str(noteMinAllTracks))
wLog("note max =  " + str(noteMaxAllTracks))
wLog("note mid range =  " + str(noteMidRange))
wLog("Start on first note timeOn in sec =  " + str(firstNoteTimeOn))
wLog("End on Last note timeOff in sec =  " + str(lastNoteTimeOff))

"""
Blender part
"""

# setBlenderUnits()
purgeUnusedDatas()
masterCollection = create_collection("MTB", bScn.collection)
hiddenCollection = create_collection("Hidden", masterCollection)
hiddenCollection.hide_viewport = True

matGlobalCustom = CreateMatGlobalCustom()

# createBlenderBGAnimation(masterCollection, "0-15", typeAnim="ZScale")
# createBlenderBGAnimation(masterCollection, "0-7", typeAnim="Light")
# createBlenderBGAnimation(masterCollection, "0-30", typeAnim="ZScale,Light")
# createStripNotes(masterCollection, "3,9,11", typeAnim="ZScale")
# createStripNotes(masterCollection, "0-15", typeAnim="Light")
# createStripNotes(masterCollection, "0-15", typeAnim="ZScale,Light")
# createWaterFall(masterCollection, "0-15", typeAnim="ZScale")
# createWaterFall(masterCollection, "0-30", typeAnim="Light")
# createWaterFall(masterCollection, "0-15", typeAnim="ZScale,Light")
# createFireworksV1(masterCollection, "0-15", typeAnim="Spread")
# createFireworksV1(masterCollection, "0-15", typeAnim="Spread,Light")
# createFireworksV2(masterCollection, "0-15", typeAnim="Spread")
# createFireworksV2(masterCollection, "0-15", typeAnim="Spread,Light")
createFountain(masterCollection, "0-15", typeAnim="fountain")
    
bScn.frame_end = math.ceil(lastNoteTimeOff + 5)*fps

createCompositorNodes()

# viewportShadingRendered()
# GUI_maximizeAeraView("VIEW_3D")
# collapseAllCollectionInOutliner()
toggle_collection_collapse(2)

# Close log file
wLog("Script Finished: %.2f sec" % (time.time() - timeStart))
flog.close()
