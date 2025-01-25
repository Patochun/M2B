"""

M2B - MIDI To Blender

Generate 3D objects animated from midifile

Author   : Patochun (Patrick M)
Mail     : ptkmgr@gmail.com
YT       : https://www.youtube.com/channel/UCCNXecgdUbUChEyvW3gFWvw
Create   : 2024-11-11
Version  : 3.0
Compatibility : Blender 4.0 and above

Licence used : GNU GPL v3
Check licence here : https://www.gnu.org/licenses/gpl-3.0.html

Comments : First version of M2B, a script to generate 3D objects animated from midifile

Usage : All parameters like midifile used and animation choices are hardcoded in the script

"""

import bpy
import bmesh
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper

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
    Simplify for focusing on notes
    
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
class MIDIChannel:
    index: int = 0
    minNote: int = 1000
    maxNote: int = 0
    notes: List[MIDINote] = field(default_factory = list)
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
from dataclasses import dataclass

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
            trackIndexUsed += 1
            tracks.append(MIDITrack(trackName, trackIndexUsed, minNote, maxNote, notes, notesUsed))
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
                    break

# Research about a collection
def find_collection(context, item):
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection

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

# Create Rectangular Plane
def createRectangularPlane(collection, name="RectanglePlane", width=1, height=1, location=(0, 0, 0)):
    bOps.mesh.primitive_plane_add(size=1, location=location)
    plane = bCon.active_object
    plane.name = name
    plane.scale[0] = width  # Adjust width (X)
    plane.scale[1] = height  # Adjust heigth (Y)
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

# Affect obj with note event
# index = 2 mean Z axis
def eventNote(obj, frameTimeOn, frameTimeOff, velocity):
    eventLenMove = int(fps * 0.1) # Lenght (in frames) before and after event for moving to it, 10% of FPS
    # set initial scale cube before acting
    obj.scale.z = 1
    obj.location.z = 0
    obj.keyframe_insert(data_path="scale", index=2, frame=frameTimeOn - eventLenMove)  # before upscaling
    obj.keyframe_insert(data_path="location", index=2, frame=frameTimeOn - eventLenMove)  
    # Upscale cube at noteNumber on timeOn
    obj.scale.z = velocity
    obj.location.z = ((velocity - 1) / 2)
    obj.keyframe_insert(data_path="scale", index=2, frame=frameTimeOn)  # upscaling
    obj.keyframe_insert(data_path="location", index=2, frame=frameTimeOn)
    # set actual scale cube before acting
    obj.scale.z = velocity
    obj.location.z = ((velocity - 1) / 2)
    obj.keyframe_insert(data_path="scale", index=2, frame=frameTimeOff - eventLenMove) # before downscaling
    obj.keyframe_insert(data_path="location", index=2, frame=frameTimeOff - eventLenMove)
    # downscale cube at noteNumber on timeOff
    obj.scale.z = 1
    obj.location.z = 0
    obj.keyframe_insert(data_path="scale", index=2, frame=frameTimeOff)  # downscaling
    obj.keyframe_insert(data_path="location", index=2, frame=frameTimeOff)

"""
Blender visualisation one BG by channel
"""
def createBlenderBGAnimation(masterCollection, maxTimeOff):
    # Create master BG collection
    BGCollect = create_collection("BarGraph", masterCollection)

    # Create model Cubes
    modelCubeBlack = addCube(hiddenCollection, "modelCubeBlack", matCubeBlack, True, (0, 0, -10), (1,1,1))
    modelCubeWhite = addCube(hiddenCollection, "modelCubeWhite", matCubeWhite, True, (0, 0, -12), (1,1,1))

    # Create cubes from channel
    channelsCenter = (channelMaxUsed - channelMinUsed) / 2
    cubeSpace = 1.2
    for channel in channels:
        if len(channel.notes) != 0:
            # Create BG Channel collection
            BGChannelCollect = create_collection("BG"+str(channel.index), BGCollect)
            for note in channel.notesUsed:
                cubeName = "Cube-"+str(channel.index)+"-"+str(note)
                offsetX = (note - noteMidRange) * cubeSpace
                offsetY = (channel.index - channelsCenter) * cubeSpace
                if "#" in midinote_to_note_alpha[note]:
                    # Duplicate the black model cube
                    cubeLinked = createDuplicateLinkedObject(BGChannelCollect, modelCubeBlack, cubeName)
                    cubeLinked.location = (offsetX, offsetY, 0)  # Change instance position
                else:
                    # Duplicate the white model cube
                    cubeLinked = createDuplicateLinkedObject(BGChannelCollect, modelCubeWhite, cubeName)
                    cubeLinked.location = (offsetX, offsetY, 0)  # Change instance position
            wLog("BarGraph - create "+str(len(channel.notesUsed))+" cubes for channel "+ str(channel.index) +" (range noteMin-noteMax) ("+str(channel.minNote)+"-"+str(channel.maxNote)+")")

    # Animate cubes accordingly to notes event
    for channel in channels:
        if len(channel.notes) != 0:
            for note in channel.notes:
                # retrieve object by is name
                cubeName = "Cube-"+str(channel.index)+"-"+str(note.noteNumber)
                obj = bDat.objects[cubeName]
                frameTimeOn = note.timeOn * fps
                frameTimeOff = note.timeOff * fps
                velocity = 8 * note.velocity
                eventNote(obj, frameTimeOn, frameTimeOff, velocity)
            wLog("BarGraph - Animate cubes for channel " +str(channel.index)+" (notesCount) ("+str(len(channel.notes))+")")
"""
End of BG visualisation
"""

"""
Blender visualisation with barrel organ

    Strip simulation from piano, note 21 (A0) to 128 (C8) => 88 notes
    A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C D E F G A B C
    0   1             2             3             4             5             6             7             8
    0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    
    X for note height
    Y for note length

    Size of Grid
    X => 88 cells for notes + 87 cells for intervals
    Y => know the minimum resolution, if we needed to have double croches

    Subdivision of note (french vs english)
    Ronde : Whole note
    Blanche : Half note
    Noire : Quarter note
    Croche : Eighth note
    Double croche : Sixteenth note
    Triple croche : Thirty-second note
    Quadruple croche : Sixty-fourth note

    ppqn means ticks per Quarter note
    ticks_per_second = ppqn * tempo / 60

"""
def createBarrelOrganStrip(masterCollection, channel, length):
    noteRange = (21, 108)  # Piano standard (A0 à C8)
    notecount = (noteRange[1]-noteRange[0]) + 1
    noteMiddle = noteRange[0] + math.ceil(notecount / 2)
    marginExtX = 0
    marginExtY = 0
    cellSizeX = 1 # size X for each note in centimeters
    intervalX = 0 # cellSizeX / 5
    cellSizeY = 1 # size for each second in centimeters
    intervalY = 0 # cellSizeY / 5
    planSizeX = (marginExtX * 2) + (notecount * cellSizeX) + ((notecount -1) * intervalX)
    length = math.ceil(length) # in second
    planSizeY = (length + (marginExtY *2)) * (cellSizeY + intervalY)
    
    # Create master Strip collection
    stripCollect = create_collection("Strip", masterCollection)

    obj = createRectangularPlane(stripCollect, "BarrelOrganStrip", planSizeX, planSizeY, (-cellSizeX / 2,planSizeY / 2,0))
    collectToRemove = create_collection("toRemove", stripCollect)

    # Create cubes from channel
    cubeModelLibrary = []  # Store unique cubes by Y size for reuse

    holeSizeX = cellSizeX
    for noteIndex, note in enumerate(channel.notes):
        holePosX = (note.noteNumber - noteMiddle) * (cellSizeX + intervalX)
        holeSizeY = round(((note.timeOff - note.timeOn) * cellSizeY),2)
        holePosY = ((marginExtY + note.timeOn) * (cellSizeY + intervalY)) + (holeSizeY / 2)

        nameOfNotePlayed = "Note-" + str(noteIndex)

        # create or duplicate linkded object note
        # Check if a cube with the same height already exists
        matchingCube = next((cube for size, cube in cubeModelLibrary if size == holeSizeY), None)
        if matchingCube:
            # Duplicate the existing note
            noteObj = createDuplicateLinkedObject(collectToRemove, matchingCube, nameOfNotePlayed)
            noteObj.location = (holePosX, holePosY, 0)  # Change instance position
        else:
            # Create a new note model
            noteModelObj = addCube(hiddenCollection, nameOfNotePlayed+"-model", matCubeWhite, False, (holePosX, holePosY, -10), (holeSizeX, holeSizeY, 1))
            cubeModelLibrary.append((holeSizeY, noteModelObj))
            # Duplicate the existing note
            noteObj = createDuplicateLinkedObject(collectToRemove, noteModelObj, nameOfNotePlayed)
            noteObj.location = (holePosX, holePosY, 0)  # Change instance position

        # Animate note
        # Be aware to animate duplicate only, never the model one
        frameTimeOn = note.timeOn * fps
        frameTimeOff = note.timeOff * fps
        velocity = 8 * note.velocity
        eventNote(noteObj, frameTimeOn, frameTimeOff, velocity)
        
    wLog("Notes Strip - create & animate "+ str(noteIndex + 1))

    # booleanModifier(obj, collectToRemove, "DIFFERENCE")
    # clearCollection(collectToRemove)

    return obj

from collections import defaultdict

def createBarrelOrganStripV2(masterCollection, channel, length):
    # Check if tempo is fixed or not
    if midiFile.tempo == 0:
        wLog("BarrelOrgan need fixed tempo for whole midi file")
        return
    lengthQuarterNote = midiFile.tempo / 1000000
    noteRange = (21, 108)  # Piano standard (A0 à C8)
    notecount = (noteRange[1]-noteRange[0]) + 1
    noteMiddle = noteRange[0] + math.ceil(notecount / 2)
    marginExtX = 0
    marginExtY = 0
    cellSizeX = 1 # size X for each note in centimeters
    intervalX = 0 # cellSizeX / 5
    cellSizeY = 1 # size for each second in centimeters
    intervalY = 0 # cellSizeY / 5
    planSizeX = (marginExtX * 2) + (notecount * cellSizeX) + ((notecount -1) * intervalX)
    length = math.ceil(length) # in second
    planSizeY = (length + (marginExtY *2)) * (cellSizeY + intervalY)

    # Créer un nouveau mesh et un objet pour le rouleau
    mesh = bDat.meshes.new("BarrelOrganStripMesh")
    obj = bDat.objects.new("BarrelOrganStrip", mesh)
    masterCollection.objects.link(obj)

    # Initialiser BMesh pour le rouleau
    segmentsCountX = notecount + (notecount - 1) + 2 # mean notes count + intervals count + 2 face for margin external X
    bm = bmesh.new()
    bmesh.ops.create_grid(
        bm,
        x_segments=int(segmentsCountX),
        # y_segments=int(planSizeY / cellSizeY),
        y_segments=int(10), # research
        size=1  # Normalisé à 1
    )

    # Redimensionner le maillage à la taille réelle
    for vert in bm.verts:
        vert.co.x *= planSizeX / 2
        # vert.co.y *= planSizeY / 2
        vert.co.y *= 5

    # face index versus note
    # 0,177 = margeExtX
    # 1 = first note
    # 2 = first intervalX
    # 3 = second note an so on
    # 178,353 = margeExtX in second line
    # 179 = first note in second line

    # work with 1/16 of note for resolution
    to_remove = []
    for note in channel.notes:
        # Dimensions et position du trou
        sizeY = (note.timeOff - note.timeOn) / (2)
        numNoteOnRow = note.noteNumber - noteRange[0] + 1
        intervalCountX = numNoteOnRow - 1
        indexOfFaceOnRow = 1 + numNoteOnRow + intervalCountX # on any row
        # Choose face on Y axis
        # wLog(str(note.noteNumber)+","+str(note.timeOff - note.timeOn))

    for face in bm.faces:
        if face.index == 0:
            to_remove.append(face)
        if face.index == 2:
            to_remove.append(face)
        if face.index == 176:
            to_remove.append(face)
        if face.index == 354:
            to_remove.append(face)

    # Supprimer les faces identifiées
    bmesh.ops.delete(bm, geom=to_remove, context='FACES')

    # Appliquer les modifications et libérer BMesh
    bm.to_mesh(mesh)
    bm.free()

"""
Main
"""

# To convert easily from midi notation to name of note
# C4 is median DO on piano keyboard and is notated 60
midinote_to_note_alpha = {
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
# filename = "pianoTest"
filename = "49f692270904997536e8f5c1070ac880"

pathMidiFile = path + "\\" + filename + ".mid"
pathAudioFile = path + "\\" + filename + ".mp3"
pathJsonFile = path + "\\" + filename + ".json"
pathLogFile = path + "\\" + filename + ".log"

# Open log file for append
flog = open(pathLogFile, "w+")

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
for track in tracks:
    noteMinAllTracks = min( noteMinAllTracks, track.minNote)
    noteMaxAllTracks = max( noteMaxAllTracks, track.maxNote)
noteMidRange = noteMinAllTracks + (noteMaxAllTracks - noteMinAllTracks) / 2
wLog("note min =  " + str(noteMinAllTracks))
wLog("note max =  " + str(noteMaxAllTracks))
wLog("note mid range =  " + str(noteMidRange))

# Create MIDI channel from all tracks
channels: List[MIDIChannel] = [MIDIChannel() for _ in range(16)]
channelMaxUsed = 0
channelMinUsed = 1000
maxTimeOff = 0
for track in tracks:
    for note in track.notes:
        maxTimeOff = max(maxTimeOff,note.timeOff)
        channelMinUsed = min(channelMinUsed, note.channel)
        channelMaxUsed = max(channelMaxUsed, note.channel)
        channels[note.channel].notes.append(MIDINote(note.channel,note.noteNumber, note.timeOn, note.timeOff, note.velocity))
        channels[note.channel].minNote = min(channels[note.channel].minNote,note.noteNumber)
        channels[note.channel].maxNote = max(channels[note.channel].maxNote,note.noteNumber)
        channels[note.channel].index = note.channel
        if note.noteNumber not in channels[note.channel].notesUsed:
            channels[note.channel].notesUsed.append(note.noteNumber)
    wLog("create channel from track "+str(track.index)+" "+track.name)
wLog("length of MIDI file in seconds =  " + str(maxTimeOff))

"""
Blender part
"""

setBlenderUnits()
masterCollection = create_collection("MTB", bScn.collection)
hiddenCollection = create_collection("Hidden", masterCollection)
hiddenCollection.hide_viewport = True

# Some materials
matCubeBlack = bDat.materials.new(name="matCube")
matCubeBlack.use_nodes = True
principled = PrincipledBSDFWrapper(matCubeBlack, is_readonly=False)
principled.base_color = (0.1, 0.1, 0.1)

matCubeWhite = bDat.materials.new(name="matCube")
matCubeWhite.use_nodes = True
principled = PrincipledBSDFWrapper(matCubeWhite, is_readonly=False)
principled.base_color = (0.9, 0.9, 0.9)

createBlenderBGAnimation(masterCollection, maxTimeOff)
# createBarrelOrganStrip(masterCollection, channels[0], maxTimeOff) # Apply when we have a reasonable amount of notes
# createBarrelOrganStripV2(masterCollection, channels[0], maxTimeOff)

bScn.frame_end = math.ceil(maxTimeOff + 5)*fps

# Close log file
wLog("Script Finished: %.2f sec" % (time.time() - timeStart))
flog.close()
