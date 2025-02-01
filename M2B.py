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

# Global list to store used colors
usedColors = []

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
                tracks.append(MIDITrack(f"{workingTracks[0].name}-ch{channel}", trackIndexUsed, minNote, maxNote, notes, notesUsed))
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
def findCollection(context, item):
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

def toggleCollectionCollapse(state):
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

# Move object to collection
def moveToCollection(collection, obj):
    # First move object to new collection
    collect_to_unlink = findCollection(bCon, obj)
    collection.objects.link(obj)
    collect_to_unlink.objects.unlink(obj)
    
    # Then set parent if _MasterLocation exists
    master_loc_name = collection.name + "_MasterLocation"
    if masterLocCollection and master_loc_name in masterLocCollection.objects:
        obj.parent = masterLocCollection.objects[master_loc_name]

# Delete collection and all childs recursively
def deleteCollectionRecursive(collection):
    # First delete all child collections recursively
    for child in collection.children:
        deleteCollectionRecursive(child)
    
    # Then delete all objects in this collection
    for obj in collection.objects:
        bDat.objects.remove(obj, do_unlink=True)
    
    # Finally remove the collection itself
    bDat.collections.remove(collection)
       
# Create collection and master location (empty axis)
def createCollection(colName, colParent, emptyLocMaster = True):
    # Delete if exists with all children
    if colName in bDat.collections:
        collection = bDat.collections[colName]
        deleteCollectionRecursive(collection)

    # create a new one
    newCollection = bDat.collections.new(colName)
    colParent.children.link(newCollection)

    if emptyLocMaster:
        # create an empty axis to be parent for all objects in the collection
        bOps.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        empty = bCon.active_object
        empty.name = colName+"_MasterLocation"

        # Check if parent collection has an empty and set parent
        parent_empty_name = colParent.name + "_MasterLocation"
        if parent_empty_name in masterLocCollection.objects:
            empty.parent = masterLocCollection.objects[parent_empty_name]

        moveToCollection(masterLocCollection, empty)

    return newCollection

"""
Purge all orphaned (unused) data in the current Blender file.
This includes unused objects, materials, textures, collections, particles, etc.
"""
def purgeUnusedDatas():
    purgedItems = 0
    dataCategories = [
        bDat.objects, bDat.curves, bDat.meshes, bDat.materials,
        bDat.textures, bDat.images, bDat.particles, bDat.node_groups,
        bDat.actions, bDat.collections, bDat.sounds
    ]
    
    for dataBlock in dataCategories:
        for item in list(dataBlock):  # Use list() to avoid modifying during iteration
            if not item.users:
                dataBlock.remove(item)
                purgedItems += 1
    
    wLog(f"Purging complete. {purgedItems} orphaned data cleaned up.")

"""
Creates custom attributes for Blender objects to control material properties.

This function adds custom properties to Blender objects that control various
material aspects through the GlobalCustomMaterial shader.

Parameters:
    obj (bpy.types.Object): Object to add custom properties to

Custom Properties Added:
    baseColor (float): 0.0-1.0
        Controls base color selection in material color ramp
        
    emissionColor (float): 0.0-1.0
        Controls emission color selection in material color ramp
        
    emissionStrength (float): 0.0-50.0
        Controls emission intensity with soft limits
        
    alpha (float): 0.0-1.0
        Controls object transparency

Returns:
    None

Usage:
    createCustomAttributes(blender_object)
"""
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

"""
Creates a Blender object with specified parameters and setup.

Creates various types of Blender objects (plane, sphere, cube, cylinder, bezier circle)
with common setup including material, custom attributes, and collection organization.

Parameters:
    objectType (BlenderObjectType): Type of object to create (PLANE, SPHERE, etc.)
    collection (bpy.types.Collection): Collection to add object to
    name (str): Name for the created object
    material (bpy.types.Material, optional): Material to apply. Defaults to None
    location (tuple, optional): (x,y,z) position. Defaults to (0,0,0)
    scale (tuple, optional): (x,y,z) scale. Defaults to (1,1,1)
    radius (float, optional): Radius for sphere/cylinder/circle. Defaults to 1.0
    height (float, optional): Height for cylinder/plane. Defaults to 1.0
    width (float, optional): Width for plane. Defaults to 1.0
    bevel (bool, optional): Apply bevel modifier to cube. Defaults to False
    resolution (int, optional): Curve resolution for bezier. Defaults to 12

Returns:
    bpy.types.Object: Created Blender object
"""
from enum import Enum

class BlenderObjectType(Enum):
    PLANE = "plane"
    SPHERE = "sphere"
    CUBE = "cube"
    CYLINDER = "cylinder"
    BEZIER_CIRCLE = "bezier_circle"

def createBlenderObject(
    objectType: BlenderObjectType,
    collection,
    name: str,
    material=None,
    location: tuple=(0,0,0),
    scale: tuple=(1,1,1),
    radius: float=1.0,
    height: float=1.0,
    width: float=1.0,
    bevel: bool=False,
    resolution: int=12
) -> bpy.types.Object:
    
    match objectType:
        case BlenderObjectType.PLANE:
            bOps.mesh.primitive_plane_add(size=1, location=location)
            obj = bCon.active_object
            obj.scale = (width, height, 1)
            
        case BlenderObjectType.SPHERE:
            bOps.mesh.primitive_ico_sphere_add(radius=radius, location=location)
            obj = bCon.active_object
            
        case BlenderObjectType.CUBE:
            bOps.mesh.primitive_cube_add(size=1, location=location)
            obj = bCon.active_object
            obj.scale = scale
            if bevel:
                bOps.object.modifier_add(type="BEVEL")
                bOps.object.modifier_apply(modifier="BEVEL")
                
        case BlenderObjectType.CYLINDER:
            bOps.mesh.primitive_cylinder_add(radius=radius, depth=height, location=location)
            obj = bCon.active_object
            obj.scale = (radius, radius, height)
            
        case BlenderObjectType.BEZIER_CIRCLE:
            bOps.curve.primitive_bezier_circle_add(location=location, radius=radius)
            obj = bCon.active_object
            obj.data.resolution_u = resolution

    # Common setup
    obj.name = name
    if material:
        obj.data.materials.append(material)
    createCustomAttributes(obj)
    moveToCollection(collection, obj)
    
    return obj

"""
Creates a linked duplicate of an object and manages its collection parenting.

Creates a copy of an object with a new name and adds it to the specified collection.
If a master location empty exists for the collection, sets it as the object's parent.

Parameters:
    collection (bpy.types.Collection): Collection to add the duplicate to
    originalObject (bpy.types.Object): Object to duplicate
    name (str): Name for the new duplicate object

Returns:
    bpy.types.Object: The created duplicate object

Usage:
    newObj = createDuplicateLinkedObject(
        collection=myCollection,
        originalObject=sourceObject,
        name="NewObjectName"
    )
"""
# Create Duplicate Instance of an Object with an another name
def createDuplicateLinkedObject(collection, originalObject, name):
    # Create a linked copy of original object
    linkedObject = originalObject.copy()
    linkedObject.name = name
    # Add object to collection specified
    collection.objects.link(linkedObject)
    # Get collection name and find matching empty in masterLocCollection
    if masterLocCollection and collection.name+"_MasterLocation" in masterLocCollection.objects:
        parentEmpty = masterLocCollection.objects[collection.name+"_MasterLocation"]
        linkedObject.parent = parentEmpty
    return linkedObject

# Set color from Trackindex and TracksCount
# Global list to store used colors
usedColors = []

def colorFromIndex(trackIndex, tracksCount):
    global usedColors
    minColorDistance = 0.1  # Minimum distance between colors (0-1)
    
    def colorDistance(color1, color2):
        return abs(color1 - color2)
    
    def isColorValid(newColor):
        if not usedColors:
            return True
        # Check distance with all used colors
        for usedColor in usedColors:
            if colorDistance(newColor, usedColor) < minColorDistance:
                return False
        return True
    
    # Generate color until valid
    attempts = 0
    maxAttempts = 50
    while attempts < maxAttempts:
        colorTrack = (trackIndex + 1) / (tracksCount + 1)
        colorTrack = (int(colorTrack * 255) ^ 0xAA) / 255
        
        if isColorValid(colorTrack):
            usedColors.append(colorTrack)
            return colorTrack
            
        attempts += 1
        trackIndex = (trackIndex + tracksCount//2) % tracksCount
    
    # Fallback if no valid color found
    return (trackIndex + 1) / (tracksCount + 1)

# Define color from note number when sharp (black) or flat (white)
def colorFromNoteNumber(noteNumber):
    if noteNumber in [1, 3, 6, 8, 10]:
        return 0.0  # Black note
    else:
        return 0.01 # White note

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

"""
Animate a Blender object based on MIDI note events and animation type.

This function handles different animation styles for visualizing MIDI notes:
- ZScale: Vertical scaling based on note velocity
- Light: Emission strength and color based on velocity
- MultiLight: Multi-colored emission based on track color
- Spread: Particle cloud expansion effect

Parameters:
    Obj (bpy.types.Object): Blender object to animate
    typeAnim (str): Animation style(s), comma-separated
    note (MIDINote): Current note to process
    previousNote (MIDINote): Previous note in sequence
    nextNote (MIDINote): Next note in sequence
    colorTrack (float): Color value for track (0.0-1.0)

Animation Timing:
    - frameT1: Note start
    - frameT2: Start transition complete
    - frameT3: End transition start
    - frameT4: Note end

Properties Animated:
    - location: (x,y,z) position
    - scale: (x,y,z) size
    - emissionColor: Material emission color
    - emissionStrength: Material emission intensity
    - modifiers: Geometry nodes parameters

Returns:
    None
"""
def noteAnimate(obj, typeAnim, note, previousNote, nextNote, colorTrack):
    eventLenMove = max(1, min(math.ceil(fps * 0.1), (note.timeOff - note.timeOn) * fps // 2))

    frameTimeOn = int(note.timeOn * fps)
    frameTimeOff = max(frameTimeOn + 2, int(note.timeOff * fps))

    frameT1, frameT2 = frameTimeOn, frameTimeOn + eventLenMove
    frameT3, frameT4 = frameTimeOff - eventLenMove, frameTimeOff

    frameTimeOffPrevious = int(previousNote.timeOff * fps) if previousNote else frameTimeOn
    frameTimeOnNext = int(nextNote.timeOn * fps) if nextNote else frameTimeOff
    
    if frameTimeOn < frameTimeOffPrevious or frameTimeOff > frameTimeOnNext:
        return
    
    brightness = 5 + note.velocity * 10

    # List of keyframes to animate
    keyframes = []

    # Handle different animation types
    for animation_type in typeAnim.split(','):
        match animation_type.strip():
            case "ZScale":
                velocity = 8 * note.velocity
                keyframes.extend([
                    (frameT1, "scale", (None, None, 1)),
                    (frameT1, "location", (None, None, 0)),
                    (frameT2, "scale", (None, None, velocity)),
                    (frameT2, "location", (None, None, (velocity - 1) / 2)),
                    (frameT3, "scale", (None, None, velocity)),
                    (frameT3, "location", (None, None, (velocity - 1) / 2)),
                    (frameT4, "scale", (None, None, 1)),
                    (frameT4, "location", (None, None, 0)),
                ])
            
            case "Light":
                adjustedVelocity = 2 * (note.velocity ** 2) if note.velocity < 0.5 else 1 - 2 * ((1 - note.velocity) ** 2)
                velocityBlueToRed = 0.02 + (0.4 - 0.02) * adjustedVelocity
                keyframes.extend([
                    (frameT1, "emissionStrength", 0.0),
                    (frameT2, "emissionStrength", brightness),
                    (frameT3, "emissionStrength", brightness),
                    (frameT4, "emissionStrength", 0.0),
                    (frameT2, "emissionColor", velocityBlueToRed),
                    (frameT3, "emissionColor", velocityBlueToRed),
                    (frameT4, "emissionColor", velocityBlueToRed),
                ])
            
            case "MultiLight":
                # If the object has an emission color from another track, average it
                if obj["emissionColor"] > 0.01:
                    colorTrack = (obj["emissionColor"] + colorTrack) / 2
                keyframes.extend([
                    (frameT1, "emissionColor", colorTrack),
                    (frameT2, "emissionColor", colorTrack),
                    (frameT3, "emissionColor", colorTrack),
                    (frameT4, "emissionColor", obj["baseColor"]),
                    (frameT1, "emissionStrength", 0.0),
                    (frameT2, "emissionStrength", brightness),
                    (frameT3, "emissionStrength", brightness),
                    (frameT4, "emissionStrength", 0.0),
                ])
            
            case "Spread":
                posZ = note.velocity * 30
                radius = min((frameT4 - frameT1) // 2, 5)
                densityCloud = obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densityCloud"].identifier
                densitySeed = obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
                
                keyframes.extend([
                    (frameT1, "location", (None, None, posZ)),
                    (frameT1, "scale", (0, 0, 0)),
                    (frameT1, "emissionStrength", 0),
                    (frameT1, f'modifiers.SparklesCloud.{densityCloud}', note.velocity / 3),
                    (frameT1, f'modifiers.SparklesCloud.{densitySeed}', random.randint(0, 1000)),
                    (frameT2, "scale", (radius, radius, radius)),
                    (frameT2, "emissionStrength", 20),
                    (frameT4, "scale", (0, 0, 0)),
                    (frameT4, "emissionStrength", 0),
                    (frameT4, f'modifiers.SparklesCloud.{densitySeed}', random.randint(0, 1000)),
                ])
            
            case _:
                wLog(f"Unknown animation type: {animation_type}")
    
    keyframes.sort(key=lambda x: (x[0], x[1]))
    
    for frame, data_path, value in keyframes:
        if isinstance(value, tuple):
            # Handle vector properties (location, scale)
            for i, v in enumerate(value):
                if v is not None:
                    val = getattr(obj, data_path) # Get vector value
                    val[i] = v  # set value with index i (0=x, 1=y, 2=z)
                    setattr(obj, data_path, val)  # Apply change
                    obj.keyframe_insert(data_path=f"{data_path}", index=i, frame=frame)
        else:
            # Handle custom properties with proper data path
            if data_path in ["emissionColor", "emissionStrength"]:
                obj[data_path] = value
                obj.keyframe_insert(data_path=f'["{data_path}"]', frame=frame)
            elif data_path.startswith('modifiers'):
                # Handle modifier properties
                modDataPath = data_path.split('.')[1]
                modDataIndex = data_path.split('.')[2]
                obj.modifiers[modDataPath][modDataIndex] = value
                data_path = f'modifiers["{modDataPath}"]["{modDataIndex}"]'
                obj.keyframe_insert(data_path=data_path, frame=frame)
            else:
                # Handle regular properties
                obj[data_path] = value
                obj.keyframe_insert(data_path=data_path, frame=frame)

"""
    Parses a range string and returns a list of numbers.
    Example input: "1-5,7,10-12"
    Example output: [1, 2, 3, 4, 5, 7, 10, 11, 12]
    return some values calculated from effective range, noteMin, noteMax, octaveCount, effectiveTrackCount
"""
def parseRangeFromTracks(rangeStr):

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
            raise ValueError(f"Invalid format : {segment}")

    wLog(f"Track filter used = {numbers}")

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

"""
Creates a global custom material with color ramps and emission control

This function creates or updates a shared material used across multiple objects.
It sets up a node network for dynamic color and emission control through object properties.

Node Setup:
    - Principled BSDF: Main shader
    - Color Ramps (HSV mode):
      - Base color: Black -> White -> Blue -> Red -> Yellow -> Green -> Cyan
      - Emission: Same color progression
    - Attribute nodes for:
      - baseColor: Controls base color selection (0.0-1.0)
      - emissionColor: Controls emission color selection (0.0-1.0)
      - emissionStrength: Controls emission intensity
      - alpha: Controls transparency

Custom Properties Used:
    - baseColor: Object property for base color selection
    - emissionColor: Object property for emission color
    - emissionStrength: Object property for emission intensity
    - alpha: Object property for transparency

Returns:
    bpy.types.Material: The created or updated material

Usage:
    material = CreateMatGlobalCustom()
    object.data.materials.append(material)
"""
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
    colorRampBase.color_ramp.color_mode = 'HSV'
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
    colorRampEmission.color_ramp.color_mode = 'HSV'
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

"""
Creates a Compositor node setup for post-processing effects

This function sets up a basic compositor node network for adding bloom/glare effects
to the final render. It creates and configures:

Node Setup:
    - Render Layers: Source of rendered image
    - Glare: Adds bloom effect
      - Type: BLOOM
      - Quality: MEDIUM
      - Mix: 0.0
      - Threshold: 5
      - Size: 4
    - Composite: Final output

Parameters:
    None

Returns:
    None

Usage:
    createCompositorNodes()
"""
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

"""
Creates a Geometry Nodes setup for generating sparkles cloud effect

This function creates a geometry nodes modifier that generates a cloud of sparkles
around a mesh. It uses point distribution on an icosphere to create the cloud effect.

Parameters:
    nameGN (str): Name for the geometry nodes group and modifier
    obj (bpy.types.Object): Blender object to add the modifier to
    sparklesMaterial (bpy.types.Material): Material to apply to sparkles

Node Setup:
    - Input icosphere for cloud volume
    - Point distribution for sparkle positions
    - Instance smaller icospheres as sparkles
    - Material assignment for sparkles

Inputs exposed:
    - radiusSparklesCloud: Overall cloud size (0.0-1.0)
    - radiusSparkles: Individual sparkle size (0.0-0.05)
    - densityCloud: Sparkle density (0-10)
    - densitySeed: Random seed for distribution (0-100000)
    - sparkleMaterial: Material for sparkles

Returns:
    None

Usage:
    createSparklesCloudGN("SparklesEffect", myObject, myMaterial)
"""
def createSparklesCloudGN(nameGN, obj, sparklesMaterial):
    # Add a modifier Geometry Nodes
    mod = obj.modifiers.new(name=nameGN, type='NODES')
    
    # Create a new node group
    nodeGroup = bDat.node_groups.new(name=nameGN, type="GeometryNodeTree")

    # Associate group with modifier
    mod.node_group = nodeGroup

    # Define inputs and outputs
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
    
    # Add necessary nodes
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
    
    # Connect nodes
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

# Retrieve octave and noteNumber from note
def extractOctaveAndNote(note):
    octave = note // 12
    noteNumber = note % 12
    return octave, noteNumber

"""
Creates a bar graph visualization for MIDI tracks in Blender.

This function creates a 3D bar graph visualization where:
- Each track gets a row of cubes
- Each cube represents a note
- X axis: Note positions (octaves)
- Y axis: Track positions
- Z axis: Note velocity animation
- Background planes show octave ranges

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("ZScale", "Light", etc)

Structure:
    - BarGraph (main collection)
        - BG-TrackN (per track collections)
            - Cubes for each note
        - BG-Plane
            - Octave separator planes

Returns:
    None

Usage:
    createBlenderBGAnimation(masterCollection, "0-15", typeAnim="ZScale,Light")
"""
def createBlenderBGAnimation(masterCollection, trackMask, typeAnim):
    wLog(f"Create a BarGraph Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, numberOfRenderedTracks = parseRangeFromTracks(trackMask)

    # Create master BG collection
    BGCollect = createCollection("BarGraph", masterCollection)

    # Create models Object
    BGModelCube = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=hiddenCollection,
        name="BGModelCube",
        material=matGlobalCustom,
        location=(0,0,-5),
        scale=(1,1,1),
        bevel=False
    )

    BGModelPlane = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=hiddenCollection,
        name="BGModelPlane",
        material=matGlobalCustom,
        location=(0,0,-5),
        height=1,
        width=1
    )
        
    # Create cubes from track
    # Parse track to create BG
    trackCenter = numberOfRenderedTracks / 2
    noteMidRange = (noteMin + noteMax) / 2
    cubeSpace = BGModelCube.scale.x * 1.2 # mean x size of cube + 20 %

    trackCount = 0
    # Parse track to create BG
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue
        # create collection
        BGTrackName = f"BG-{trackIndex}-{track.name}"
        BGTrackCollect = createCollection(BGTrackName, BGCollect)
        trackCount += 1

        # one cube per note used
        for note in track.notesUsed:
            # create cube
            cubeName = f"Cube-{trackIndex}-{note}"
            offsetX = (note - noteMidRange) * cubeSpace
            offsetY = (trackCount - trackCenter - 1) * cubeSpace + cubeSpace / 2
            cubeLinked = createDuplicateLinkedObject(BGTrackCollect, BGModelCube, cubeName)
            cubeLinked.location = (offsetX, offsetY, 0)
            cubeLinked["baseColor"] = colorFromNoteNumber(note % 12)
                
        wLog(f"BarGraph - create {len(track.notesUsed)} cubes for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

    # Create a plane by octave to have a visualisation for them
    # minnote and maxnote are usefull to know the range of octave
    minOctave = noteMin // 12
    maxOctave = noteMax // 12
    
    BGPlaneCollect = createCollection("BG-Plane", BGCollect)

    planPosXOffset = (((noteMidRange % 12) - 5) * cubeSpace) - (cubeSpace / 2)
    for octave in range(minOctave, maxOctave + 1):
        planSizeX = 12 * cubeSpace
        planSizeY = trackCount * cubeSpace
        planPosX = (octave - (noteMidRange // 12)) * 12 * cubeSpace
        planPosX -= planPosXOffset
        planeName = f"Plane-{octave}"
        obj = createDuplicateLinkedObject(BGPlaneCollect, BGModelPlane, planeName)
        obj.scale = (planSizeX, planSizeY, 1)
        obj.location = (planPosX, 0, (-BGModelCube.scale.z / 2)*1.05)
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
            cubeName = f"Cube-{trackIndex}-{note.noteNumber}"
            noteObj = bDat.objects[cubeName]
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote, colorTrack)

        wLog(f"BarGraph - Animate cubes for track {trackIndex} (notesCount) ({len(track.notes)})")
        
    return

import re

"""
Creates a strip-based visualization of MIDI notes with animations.

This function creates a vertical strip visualization where:
- Each note is represented by a rectangle
- X axis: Note pitch and track offset
- Y axis: Time (note start/duration)
- Background plane shows total time range
- Notes are colored by track

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("ZScale", "Light", etc)

Structure:
    - StripNotes (main collection)
        - Notes-TrackN (per track collections)
            - Note rectangles
        - NotesStripPlane (background)

Returns:
    bpy.types.Object: The created background plane object

"""
def createStripNotes(masterCollection, trackMask, typeAnim):

    wLog(f"Create a Strip Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, trackProcessed = parseRangeFromTracks(trackMask)

    # Create models Object
    stripModelCube = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=hiddenCollection,
        name="StripNotesModelCube",
        material=matGlobalCustom,
        location=(0,0,-5),
        scale=(1,1,1),
        bevel=False
    )

    stripCollect = createCollection("StripNotes", masterCollection)

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
        notesCollection = createCollection(f"Notes-Track-{trackIndex}", stripCollect)

        sizeX = cellSizeX

        colorTrack = colorFromIndex(trackIndex, trackProcessed)

        for noteIndex, note in enumerate(track.notes):
            posX = ((note.noteNumber - noteMiddle) * (cellSizeX + intervalTracks)) + offSetX + (sizeX / 2)
            sizeY = round(((note.timeOff - note.timeOn) * cellSizeY),2)
            posY = ((marginExtY + note.timeOn) * (cellSizeY + intervalY)) + (sizeY / 2)
            nameOfNotePlayed = f"Note-{trackIndex}-{noteIndex}"

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
            
        wLog(f"Notes Strip track {trackIndex} - create & animate {noteIndex + 1}")

    # Create background plane
    obj = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=stripCollect,
        name="NotesStripPlane",
        material=matGlobalCustom,
        location=(0, planSizeY / 2, (-stripModelCube.scale.z / 2)*1.05),
        width=planSizeX,
        height=planSizeY
    )
    obj["baseColor"] = 0.01 # White

    return obj

"""
Creates a waterfall visualization of MIDI notes with animated camera movement.

This function creates a waterfall view where:
- Uses strip notes visualization as base
- Adds orthographic camera that follows notes
- Smooth vertical scrolling through timeline
- Notes appear as they are played

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply

Structure:
    - StripNotes (base visualization)
    - Camera
        - Orthographic setup
        - Linear vertical movement
        - Follows note timing

Returns:
    None
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
    FirstNotePlayed = f"Note-{noteMinTimeOn[0]}-{noteIndex}"
    noteIndex = tracks[noteMaxTimeOff[0]].notes.index(noteMaxTimeOff[1])
    LastNotePlayed = f"Note-{noteMaxTimeOff[0]}-{noteIndex}"
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

    # Make animation linear
    action = cameraObj.animation_data.action  # Get animation action
    fcurve = action.fcurves.find(data_path="location", index=1)  # F-Curve for Y axis

    if fcurve:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'  # Set interpolation to 'LINEAR'

"""
Creates a fireworks visualization where notes are represented as exploding sparkle clouds.

This function creates a fireworks display where:
- Notes are arranged in a grid pattern
- Each note is represented by a sphere with sparkle particles
- Spheres explode with particles when notes are played
- Colors are assigned by track

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("Spread", "MultiLight", etc)

Structure:
    - FireworksV1 (main collection)
        - FW-TrackN (per track collections)
            - Sphere objects with sparkle clouds
            - Each sphere positioned by note/octave

Grid Layout:
    - X axis: Notes within octave (0-11)
    - Y axis: Octaves
    - Z axis: Animation space for explosions

Returns:
    None
"""
def createFireworksV1(masterCollection, trackMask, typeAnim):

    wLog(f"Create a Fireworks V1 Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create master BG collection
    FWCollect = createCollection("FireworksV1", masterCollection)

    # Create model Sphere
    FWModelSphere = createBlenderObject(
        BlenderObjectType.SPHERE,
        collection=hiddenCollection,
        name="FWModelSphere",
        material=matGlobalCustom,
        location=(0,0,-5),
        radius=1
    )

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
        FWTrackName = f"FW-{trackIndex}-{track.name}"
        FWTrackCollect = createCollection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            noteCount += 1
            # create sphere
            sphereName = f"Sphere-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelSphere, sphereName)
            sphereLinked.location = ((note % 12) * spaceX - offsetX, (note // 12) * spaceY - offsetY, 0)
            sphereLinked.scale = (0,0,0)
            sphereLinked["baseColor"] = colorTrack
            sphereLinked["emissionColor"] = colorTrack
            sparkleCloudSeed = sphereLinked.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
            sphereLinked.modifiers["SparklesCloud"][sparkleCloudSeed] = noteCount

        wLog(f"Fireworks - create {noteCount} sparkles cloud for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

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
            objName = f"Sphere-{trackIndex}-{note.noteNumber}"
            noteObj = bDat.objects[objName]
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote, colorTrack)

        wLog(f"Fireworks - Animate sparkles cloud for track {trackIndex} (notesCount) ({len(track.notes)})")

    return


"""
Creates a particle-based fireworks visualization using Blender's particle system.

This function creates an advanced fireworks display where:
- Notes are arranged in a 3D grid (X: notes, Y: octaves, Z: tracks)
- Each note has an emitter and sparkle objects
- Emitters shoot particles based on note timing
- Particles inherit track colors and note velocities

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply

Structure:
    - FireworksV2 (main collection)
        - FW-TrackN (per track collections)
            - Emitter spheres
            - Sparkle particles
            - Particle systems

Grid Layout:
    - X axis: Notes within octave (0-11)
    - Y axis: Octaves
    - Z axis: Track layers

Particle System:
    - Count: 100 particles per note
    - Lifetime: 50 frames
    - Velocity: Based on note velocity
    - Gravity: Reduced to 10%
    - Size variation: 20%

Returns:
    None
"""
def createFireworksV2(masterCollection, trackMask, typeAnim):

    wLog(f"Create a Fireworks V2 Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create master BG collection
    FWCollect = createCollection("FireworksV2", masterCollection)

    # Create model objects
    FWModelEmitter = createBlenderObject(
        BlenderObjectType.SPHERE,
        collection=hiddenCollection,
        name="FWV2Emitter",
        material=matGlobalCustom,
        location=(0,0,-5),
        radius=1
    )

    FWModelSparkle = createBlenderObject(
        BlenderObjectType.SPHERE,
        collection=hiddenCollection,
        name="FWV2Sparkles",
        material=matGlobalCustom,
        location=(0,0,-5),
        radius=0.1
    )

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
        FWTrackName = f"FW-{trackIndex}-{track.name}"
        FWTrackCollect = createCollection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            # create sphere
            pX = (note % 12) * spaceX - offsetX
            pY = ((note // 12) - octaveCenter) * spaceY
            pZ = (trackIndex - trackCenter) * spaceZ
            emitterName = f"noteEmitter-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelEmitter, emitterName)
            sphereLinked.location = (pX, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["alpha"] = 0.0
            sparkleName = f"noteSparkles-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(hiddenCollection, FWModelSparkle, sparkleName)
            sphereLinked.location = (pX, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["baseColor"] = colorTrack
            sphereLinked["emissionColor"] = colorTrack

        wLog(f"Fireworks V2 - create {len(track.notesUsed)} sparkles cloud for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

        # create animation
        noteCount = 0
        for currentIndex, note in enumerate(track.notes):
            noteCount += 1
            
            frameTimeOn = int(note.timeOn * fps)
            frameTimeOff = int(note.timeOff * fps)

            emitterName = f"noteEmitter-{trackIndex}-{note.noteNumber}"
            emitterObj = bDat.objects[emitterName]

            # Add a particle system to the object
            psName = f"PS-{noteCount}"
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
            sparkleName = f"noteSparkles-{trackIndex}-{note.noteNumber}"
            sparkleObj = bDat.objects[sparkleName]
            sparkleObj["emissionStrength"] = Brigthness

            particleSettings.instance_object = sparkleObj
            particleSettings.particle_size = 1.0  # Size of particles
            particleSettings.size_random = 0.2    # 20 % of variability

            # sparkleObj.scale = (1,1,1)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOn)

            # sparkleObj.scale = (0,0,0)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOff)

        wLog(f"Fireworks V2 - animate {noteCount} sparkles cloud for track {trackIndex}")

    # Animation

    return

"""
Creates a fountain-style MIDI visualization with particle trajectories.

This function creates a circular fountain display where:
- Notes are arranged in concentric rings by octave
- Emitters move along circular path
- Particles shoot from emitters to note targets
- Physics-based particle trajectories

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("fountain")

Structure:
    - Fountain (main collection)
        - FountainTargets (note target planes)
        - FountainEmitters (moving particle emitters)
            - Trajectory curve
            - Track-based emitters
            - Particle systems

Physics Setup:
    - Particle trajectories calculated with gravity
    - Collision detection on targets
    - Linear emitter movement on curve
    - Particle lifetime based on travel time

Returns:
    None
"""
def createFountain(masterCollection, trackMask, typeAnim):

    wLog(f"Create a Fountain Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tacksProcessed = parseRangeFromTracks(trackMask)

    # Create Collection
    fountainCollection = createCollection("Fountain", masterCollection)

    # Create model objects
    fountainModelPlane = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=hiddenCollection,
        name="fountainModelPlane",
        material=matGlobalCustom,
        location=(0, 0, -10),
        height=1,
        width=1
    )

    fountainModelParticle = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=hiddenCollection,
        name="fountainModelParticle",
        material=matGlobalCustom,
        location=(2,0,-10),
        scale=(1,1,1),
        bevel=False
    )

    fountainModelEmitter = createBlenderObject(
        BlenderObjectType.CYLINDER,
        collection=hiddenCollection,
        name="fountainModelEmitter",
        material=matGlobalCustom,
        location=(4,0,-10),
        radius=1,
        height=1
    )

    # Create Target Collection
    fountainTargetCollection = createCollection("FountainTargets", fountainCollection)

    # Construction of the fountain Targets
    theta = math.radians(360)  # 2 Pi, just one circle
    alpha = theta / 12  # 12 is the Number of notes per octave
    for note in range(132):
        octave, numNote = extractOctaveAndNote(note)
        targetName = f"Target-{numNote}-{octave}"
        targetObj = createDuplicateLinkedObject(fountainTargetCollection, fountainModelPlane, targetName)
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

    # Create Target Collection
    fountainEmitterCollection = createCollection("FountainEmitters", fountainCollection)

    # Create circle curve for trajectory of emitters
    radiusCurve = 20
    fountainEmitterTrajectory = createBlenderObject(
        BlenderObjectType.BEZIER_CIRCLE,
        collection=fountainEmitterCollection,
        name="fountainEmitterTrajectory",
        location=(0, 0, 3),
        radius=radiusCurve
    )

    # Animate circle curve with rotation
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

    trackCount = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        colorTrack = colorFromIndex(trackIndex, len(tracks))
        trackCount += 1

        # Particle
        particleName = f"Particle-{trackIndex}-{track.name}"
        particleObj = createDuplicateLinkedObject(hiddenCollection, fountainModelParticle, particleName)
        particleObj.name = particleName
        particleObj.location = (trackIndex * 2, 0, -12)
        particleObj.scale = (0.3,0.3,0.3)
        particleObj["baseColor"] = colorTrack
        particleObj["emissionColor"] = colorTrack
        particleObj["emissionStrength"] = 8.0

        # Emitter around the targets
        emitterName = f"Emitter-{trackIndex}-{track.name}"
        emitterObj = createDuplicateLinkedObject(fountainEmitterCollection, fountainModelEmitter, emitterName)

        # Add Clamp To constraint
        clampConstraint = emitterObj.constraints.new(type='CLAMP_TO')
        clampConstraint.target = fountainEmitterTrajectory
        clampConstraint.use_cyclic = True  # Enable cyclic for closed curve

        # Calculate position on curve (0 to 1)
        curvePosition = trackCount / tacksProcessed
        clampConstraint.target_space = 'LOCAL'

        emitterObj.location = (radiusCurve * 2 * curvePosition, 0, 0)
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
            pSystemName = f"ParticleSystem-{octave}-{currentIndex}"
            particleSystem = emitterObj.modifiers.new(name=pSystemName, type='PARTICLE_SYSTEM')
            pSettingName = f"ParticleSettings-{octave}-{currentIndex}"
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
            targetName = f"Target-{numNote}-{octave}"
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

        wLog(f"Fountain - create {currentIndex} particles for track {trackIndex}")

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

            # animate target
            octave, numNote = extractOctaveAndNote(note.noteNumber)
            targetName = f"Target-{numNote}-{octave}"
            noteObj = bDat.objects[targetName]
            noteAnimate(noteObj, "MultiLight", note, previousNote, nextNote, colorTrack)

        wLog(f"Fountain - animate targets with {currentIndex} notes")

    return

"""
Main
"""

timeStart = time.time()

# path and name of midi file and so on - temporary => replaced when this become an Blender Extension
path = "W:\\MIDI\\Samples"
# filename = "MIDI Sample"
# filename = "MIDI Sample C3toC4"
# filename = "pianoTest"
# filename = "sampleFountain"
# filename = "T1_CDL" # midifile 1
# filename = "Albinoni"
filename = "robert_miles-children"
# filename = "RushE"
# filename = "MIDI-Testing"
# filename = "49f692270904997536e8f5c1070ac880" # Midifile 1 - Multi tracks classical
# filename = "PianoClassique3Tracks978Mesures"
# filename = "ManyTracks" # Midifile 1 - 28 tracks
# filename = "067dffc37b3770b4f1c246cc7023b64d" # One channel Biggest 35188 notes
# filename = "a4727cd831e7aff3df843a3da83e8968" # Midifile 0 -  1 track with several channels
# filename = "4cd07d39c89de0f2a3c7b2920a0e0010" # Midifile 0 - 1 track with several channels

pathMidiFile = path + "\\" + filename + ".mid"
pathAudioFile = path + "\\" + filename + ".mp3"
pathLogFile = path + "\\" + filename + ".log"

# Open log file for append
flog = open(pathLogFile, "w+")

wLog(f"Python version = {sys.version_info}")
wLog(f"Blender version = {bpy.app.version_string}")

# Hope to have 50 fps at min
fps = bScn.render.fps
wLog(f"FPS = {fps}")

# Import midi Datas
midiFile, TempoMap, tracks = readMIDIFile(pathMidiFile)

wLog(f"Midi file path = {pathMidiFile}")
wLog(f"Midi type = {midiFile.midiFormat}")
wLog(f"PPQN = {midiFile.ppqn}")
wLog(f"Number of tracks = {len(tracks)}")

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

noteMidRangeAllTracks = noteMinAllTracks + (noteMaxAllTracks - noteMinAllTracks) / 2
wLog(f"note min = {noteMinAllTracks}")
wLog(f"note max = {noteMaxAllTracks}")
wLog(f"note mid range = {noteMidRangeAllTracks}")
wLog(f"Start on first note timeOn in sec = {firstNoteTimeOn}")
wLog(f"End on Last note timeOff in sec = {lastNoteTimeOff}")

"""
Blender part
"""

# setBlenderUnits()
masterCollection = createCollection("M2B", bScn.collection, False)
purgeUnusedDatas()

masterLocCollection = createCollection("MasterLocation", masterCollection, False)
hiddenCollection = createCollection("Hidden", masterCollection)
hiddenCollection.hide_viewport = True

matGlobalCustom = CreateMatGlobalCustom()

# createBlenderBGAnimation(masterCollection, "8-15", typeAnim="ZScale")
# createBlenderBGAnimation(masterCollection, "0-7", typeAnim="Light")
createBlenderBGAnimation(masterCollection, "3-4,7-12,14-20", typeAnim="ZScale,Light")
# createStripNotes(masterCollection, "3,9,11", typeAnim="ZScale")
# createStripNotes(masterCollection, "0-15", typeAnim="Light")
# createStripNotes(masterCollection, "0-15", typeAnim="ZScale,Light")
# createWaterFall(masterCollection, "0-15", typeAnim="ZScale")
# createWaterFall(masterCollection, "0-30", typeAnim="Light")
# createWaterFall(masterCollection, "0-15", typeAnim="ZScale,Light")
# createFireworksV1(masterCollection, "6-8", typeAnim="Spread")
# createFireworksV1(masterCollection, "0-15", typeAnim="Spread,Light")
# createFireworksV2(masterCollection, "6-8", typeAnim="Spread")
# createFireworksV2(masterCollection, "0-15", typeAnim="Spread,Light")
createFountain(masterCollection, "0,2,5,6,13", typeAnim="fountain")
    
bScn.frame_end = math.ceil(lastNoteTimeOff + 5)*fps

createCompositorNodes()

# viewportShadingRendered()
# GUI_maximizeAeraView("VIEW_3D")
# collapseAllCollectionInOutliner()
toggleCollectionCollapse(2)

# Close log file
wLog(f"Script Finished: {time.time() - timeStart:.2f} sec")
flog.close()
