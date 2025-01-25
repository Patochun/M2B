"""

M2B - MIDI To Blender

Generate 3D objects animated from midifile

Author   : Patochun (Patrick M)
Mail     : ptkmgr@gmail.com
YT       : https://www.youtube.com/channel/UCCNXecgdUbUChEyvW3gFWvw
Create   : 2024-11-11
Version  : 6.0
Compatibility : Blender 4.0 and above

Licence used : GNU GPL v3
Check licence here : https://www.gnu.org/licenses/gpl-3.0.html

Comments : First version of M2B, a script to generate 3D objects animated from midifile

Usage : All parameters like midifile used and animation choices are hardcoded in the script

"""

import bpy
import bmesh
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
import sys

# Global blender objects
bDat = bpy.data
bCon = bpy.context
bScn = bCon.scene
bOps = bpy.ops

"""
Module MIDI for importation from https://github.com/JacquesLucke/animation_nodes
Code written by OMAR Emara and modified slightly accordingly to my needs
Add :
    add noteMin & noteMax inside track object
    add notesUsed inside track object
    add track only if exist notes inside into tracks
    add trackIndexUsed vs trackIndex
    
Integrated directly here for simplification
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
            # self.noteOnTable[key] = NoteOnRecord(self.timeInSeconds, event.velocity / 127)

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
    tracks = []
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
            tracks.append(MIDITrack(trackName, trackIndexUsed, minNote, maxNote, notes, notesUsed))
            trackIndexUsed += 1
    return midiFile, tempoMap, tracks

"""
End of Module MIDI for importation
"""

"""
Start of original code
"""

import os
import time
import math

# write to screen and log
def wLog(toLog):
    print(toLog)
    flog.write(toLog+"\n")

# Define unit system
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

def collapseCollectionInOutliner(collectionName):
    """
    Collapses a collection in the outliner by name.
    Args:
        collection_name (str): The name of the collection to collapse.
    """
    # Iterate through all areas in the current screen to find the OUTLINER
    for area in bCon.screen.areas:
        if area.type == 'OUTLINER':
            # Set the context override for the OUTLINER area
            with bCon.temp_override(area=area):
                # Loop through the outliner and attempt to find the collection
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = {
                            'area': area,
                            'region': region,
                            'window': bpy.context.window,
                            'screen': bpy.context.screen,
                        }
                        try:
                            bOps.outliner.item_openclose(override, open=False)
                        except RuntimeError as e:
                            print(f"Failed to collapse collection '{collectionName}': {e}")
            break
    else:
        print("No OUTLINER area found in the current context.")
       
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

def purge_unused_data():
    """
    Purge all orphaned (unused) data in the current Blender file.
    This includes unused objects, materials, textures, collections, etc.
    """
    
    # Purge orphaned objects, meshes, lights, cameras, and other data
    # bOps.outliner.orphan_data()
    
    # Force update in case orphan purge needs cleanup
    # bCon.view_layer.update()
    
    # Clear orphaned collections
    for collection in bDat.collections:
        if not collection.objects:
            # If the collection has no objects, remove it
            bDat.collections.remove(collection)

    # Clean orphaned meshes
    for mesh in bDat.meshes:
        if not mesh.users:
            bDat.meshes.remove(mesh)
    
    # Clean orphaned materials
    for mat in bDat.materials:
        if not mat.users:
            bDat.materials.remove(mat)

    # Clean orphaned textures
    for tex in bDat.textures:
        if not tex.users:
            bDat.textures.remove(tex)
    
    # Clean orphaned images
    for img in bDat.images:
        if not img.users:
            bDat.images.remove(img)

    # Log the results
    wLog("Purging complete. Orphaned data cleaned up.")

def createCustomAttributes(obj):
    # Add custom attributes
    obj["baseColor"] = 0.0  # Base color as a float
    obj.id_properties_ui("baseColor").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Color factor for base Color"
    )

    obj["emissionStrength"] = 0.0  # Emission strength as a float
    obj.id_properties_ui("emissionStrength").update(
        min=0.0,  # Minimum value
        soft_min=0.0,  # Soft minimum for UI
        soft_max=10.0,  # Soft maximum for UI
        description="Strength of the emission"
    )

    obj["emissionColor"] = 0.0  # Emission color as a float
    obj.id_properties_ui("emissionColor").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Color factor for the emission (0 to 1)"
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

# Create Duplicate Instance of an Object with an another name
def createDuplicateLinkedObject(collection, originalObject, name):
    # Créer une copie liée de l'objet original
    linkedObject = originalObject.copy()
    linkedObject.name = name
    # Ajouter l'instance à la collection spécifiée
    collection.objects.link(linkedObject)
    return linkedObject

# Set a new material with Object link mode to object
# If typeAnim contains "Light", material needs to be independent
def setMaterialWithObjectLink(obj, typeAnim, color):

    # If typeAnim contains "Light" => create a new material independent of shared mesh
    # else do nothing, keep material from obj
    if "Light" in typeAnim:
        # Ensure material is independent of shared mesh
        # Create new material
        matNew = bpy.data.materials.new(name="Material-" + obj.name)
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
def noteAnimate(Obj, typeAnim, note, previousNote, nextNote):

    eventLenMove = math.ceil(fps * 0.1) # Length (in frames) before and after event for moving to it, 10% of FPS

    frameTimeOn = int(note.timeOn * fps)
    frameTimeOff = int(note.timeOff * fps)

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
            case "Scale":
                velocity = 8 * note.velocity
                # set initial scale cube before acting (T1)
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
            case "Light":
                brightness = note.velocity * 20 # 2 ** (velocity ** 10)
                # set initial lighing before note On (T1)
                Obj["emissionColor"] = note.velocity
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT1)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT1)
                # Upscale lighting on timeOn (T2)
                Obj["emissionStrength"] = brightness
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT2)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT2)
                # Keep actual lighting before note Off (T3)
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT3)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT3)
                # reset ligthing to initial state on timeOff (T4)
                Obj["emissionStrength"] = 0.0
                Obj.keyframe_insert(data_path='["emissionColor"]', frame=frameT4)
                Obj.keyframe_insert(data_path='["emissionStrength"]', frame=frameT4)
            case _:
                wLog("I don't now anything about "+typeAnim)

# Parse a formated range in string and return a liste of values
def parseRange(rangeStr):
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
    return numbers

# Create a global material with custom object attributes for base color, emission color and emission strength
def CreateMatGlobalCustom():
    materialName = "GlobalCubeMaterial"
    if materialName not in bpy.data.materials:
        mat = bpy.data.materials.new(name=materialName)
        mat.use_nodes = True
    else:
        mat = bpy.data.materials[materialName]

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
    colorRampBase.color_ramp.interpolation = 'LINEAR'  # Ensure linear interpolation
    colorRampBase.color_ramp.elements.new(0.01)  # Add a stop at 0.20
    colorRampBase.color_ramp.elements.new(0.02)  # Add a stop at 0.20
    colorRampBase.color_ramp.elements.new(0.20)  # Add a stop at 0.20
    colorRampBase.color_ramp.elements.new(0.40)  # Add a stop at 0.40
    colorRampBase.color_ramp.elements.new(0.60)  # Add a stop at 0.60
    colorRampBase.color_ramp.elements.new(0.80)  # Add a stop at 0.80
    colorRampBase.color_ramp.elements[0].color = (0, 0, 0, 1)  # Black 0.0
    colorRampBase.color_ramp.elements[1].color = (1, 1, 1, 1)  # White 0.01
    colorRampBase.color_ramp.elements[2].color = (1, 0, 0, 1)  # Red 0.02
    colorRampBase.color_ramp.elements[3].color = (1, 1, 0, 1)  # Yellow 0.2
    colorRampBase.color_ramp.elements[4].color = (0, 1, 0, 1)  # Green 0.4
    colorRampBase.color_ramp.elements[5].color = (0, 1, 1, 1)  # Cyan 0.6
    colorRampBase.color_ramp.elements[6].color = (0, 0, 1, 1)  # Blue 0.8
    colorRampBase.color_ramp.elements[7].color = (1, 0, 1, 1)  # Purple 1.0

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
    colorRampEmission.color_ramp.interpolation = 'LINEAR'  # Ensure linear interpolation
    colorRampEmission.color_ramp.elements[0].color = (0, 0, 1, 1)  # Blue
    colorRampEmission.color_ramp.elements[1].color = (1, 0, 0, 1)  # Red

    # Connect the nodes
    links.new(attributeBaseColor.outputs["Fac"], colorRampBase.inputs["Fac"])  # Emission color
    links.new(attributeEmissionStrength.outputs["Fac"], principledBSDF.inputs["Emission Strength"])  # Emission strength
    links.new(attributeEmissionColor.outputs["Fac"], colorRampEmission.inputs["Fac"])  # Emission color
    links.new(colorRampBase.outputs["Color"], principledBSDF.inputs["Base Color"])  # Base color
    links.new(colorRampEmission.outputs["Color"], principledBSDF.inputs["Emission Color"])  # Emission color
    links.new(principledBSDF.outputs["BSDF"], output.inputs["Surface"])  # Output surface

    return mat

def createCompositorNodes():
    # Enable the compositor
    bCon.scene.use_nodes = True
    nodeTree = bCon.scene.node_tree

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
    glareNode.quality = 'HIGH'
    glareNode.mix = 0.0
    glareNode.threshold = 1.6
    glareNode.size = 6

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
    bpy.context.scene.use_nodes = True

    # Ensure compositor updates are enabled
    bpy.context.scene.render.use_compositing = True
    bpy.context.scene.render.use_sequencer = False  # Disable sequencer if not needed
    
    return

"""
Blender visualisation one BarGraph by track
"""
def createBlenderBGAnimation(masterCollection, trackMask, typeAnim):
    # noteMidRange is a global variable

    wLog("Create a BarGraph Animation type="+typeAnim)

    listOfSelectedTrack = parseRange(trackMask)

    # Create master BG collection
    BGCollect = create_collection("BarGraph", masterCollection)

    # Create model Cubes
    BGModelCube = addCube(hiddenCollection, "BGModelCube", matGlobalCustom, False, (0, 0, -5), (1,1,1))

    # Create cubes from track
    trackCenter = (len(tracks)-1) / 2
    cubeSpace = BGModelCube.scale.x * 1.2 # mean x size of cube + 20 %

    trackCount = 0
    noteMin = 1000
    noteMax = 0
    # Parse track to create BG
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

        noteMin = min(noteMin, track.minNote)
        noteMax = max(noteMax, track.maxNote)
        # create collection
        BGTrackName = "BG-"+str(trackIndex)
        BGTrackCollect = create_collection(BGTrackName, BGCollect)
        trackCount += 1

        # one cube per note used
        for note in track.notesUsed:
            # create cube
            cubeName = "Cube-"+str(trackIndex)+"-"+str(note)
            offsetX = (note - noteMidRange) * cubeSpace
            offsetY = (trackIndex - trackCenter) * cubeSpace
            cubeLinked = createDuplicateLinkedObject(BGTrackCollect, BGModelCube, cubeName)
            cubeLinked.location = (offsetX, offsetY, 0)
            if "#" in numNoteToAlpha[note]:
                cubeLinked["baseColor"] = 0.0 # Black
            else:
                cubeLinked["baseColor"] = 0.01 # White
                
        wLog("BarGraph - create "+str(len(track.notesUsed))+" cubes for track "+ str(trackIndex) +" (range noteMin-noteMax) ("+str(track.minNote)+"-"+str(track.maxNote)+")")

    planSizeX = (noteMax-noteMin+1) * cubeSpace
    planSizeY = trackCount * cubeSpace
    obj = createRectangularPlane(BGCollect, "BGPlane", matGlobalCustom, planSizeX, planSizeY, (0, 0, (-BGModelCube.scale.z / 2)*1.05))
    obj["baseColor"] = 0.01 # White

    # Animate cubes accordingly to notes event
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue

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
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote)

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

    listOfSelectedTrack = parseRange(trackMask)

    stripModelCube = addCube(hiddenCollection, "StripNotesModelCube", matGlobalCustom, False, (0, 0, -5), (1,1,1))
    stripCollect = create_collection("StripNotes", masterCollection)

    # Evaluate the real count of track processed
    # For all tracks processed : 
    # - minNote played
    # - maxNote played
    # - length in sec
    trackProcessed = 0
    noteMin = 1000
    noteMax = 0
    length = 0
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in listOfSelectedTrack:
            continue
        trackProcessed += 1
        noteMin = min(noteMin, track.minNote)
        noteMax = max(noteMax, track.maxNote)
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
        colorTrack = (trackIndex + 1) / (len(tracks) + 1) # color for track
        colorTrack = (int(colorTrack * 255) ^ 0xAA) /255 # XOR operation to get a different color

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
            noteAnimate(noteObj, typeAnim, note, previousNote, nextNote)
           
            
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

    listOfSelectedTrack = parseRange(trackMask)

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
    cameraData = bpy.data.cameras.new(name="Camera")
    cameraObj = bpy.data.objects.new("Camera", cameraData)
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
    bCon.scene.camera = cameraObj

    # Rendre l'animation linéaire
    action = cameraObj.animation_data.action  # Récupérer l'action d'animation de l'objet
    fcurve = action.fcurves.find(data_path="location", index=1)  # F-Curve pour l'axe Y

    if fcurve:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'  # Définir l'interpolation sur 'LINEAR'

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

timeStart = time.time()

# path and name of midi file and so on - temporary => replaced when this become an Blender Extension
path = "W:\\MIDI\\Samples"
# filename = "MIDI Sample"
# filename = "MIDI Sample C3toC4"
# filename = "pianoTest"
filename = "sampleFountain"
# filename = "T1_CDL"
# filename = "RushE"
# filename = "MIDI-Testing"
# filename = "T1"
# filename = "49f692270904997536e8f5c1070ac880" # Multi channel classical
# filename = "PianoClassique3Tracks978Mesures"
# filename = "ManyTracks"
# filename = "067dffc37b3770b4f1c246cc7023b64d" # One channel Biggest 35188 notes
# filename = "a4727cd831e7aff3df843a3da83e8968" # Next test
# filename = "4cd07d39c89de0f2a3c7b2920a0e0010"

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

setBlenderUnits()
purge_unused_data()
masterCollection = create_collection("MTB", bScn.collection)
hiddenCollection = create_collection("Hidden", masterCollection)
hiddenCollection.hide_viewport = True

matGlobalCustom = CreateMatGlobalCustom()

# createBlenderBGAnimation(masterCollection, "0-15", typeAnim="Scale")
# createBlenderBGAnimation(masterCollection, "0-15", typeAnim="Light")
# createBlenderBGAnimation(masterCollection, "0-30", typeAnim="Light,Scale")
# createStripNotes(masterCollection, "3,9,11", typeAnim="Scale")
# createStripNotes(masterCollection, "0-15", typeAnim="Light")
# createWaterFall(masterCollection, "0-15", typeAnim="Scale")
createWaterFall(masterCollection, "0-15", typeAnim="Light")
# createWaterFall(masterCollection, "0-15", typeAnim="Scale,Light")

bScn.frame_end = math.ceil(lastNoteTimeOff + 5)*fps
createCompositorNodes()
viewportShadingRendered()

# Close log file
wLog("Script Finished: %.2f sec" % (time.time() - timeStart))
flog.close()
