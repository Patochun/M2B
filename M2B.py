"""

M2B - MIDI To Blender

Generate 3D objects animated from midifile

Author   : Patochun (Patrick M)
Mail     : ptkmgr@gmail.com
YT       : https://www.youtube.com/channel/UCCNXecgdUbUChEyvW3gFWvw
Create   : 2024-11-11
Version  : 1.0
Compatibility : Blender 4.0 and above

Licence used : GNU GPL v3
Check licence here : https://www.gnu.org/licenses/gpl-3.0.html

Comments : First version of M2B, a script to generate 3D objects animated from midifile

Usage : All parameters like midifile used and animation choices are hardcoded in the script

"""

import bpy
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper

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
        text = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, text)

@dataclass
class CopyrightEvent:
    deltaTime: int
    copyright: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        copyright = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, copyright)

@dataclass
class TrackNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, name)

@dataclass
class InstrumentNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, name)

@dataclass
class LyricEvent:
    deltaTime: int
    lyric: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        lyric = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, lyric)

@dataclass
class MarkerEvent:
    deltaTime: int
    marker: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        marker = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, marker)

@dataclass
class CuePointEvent:
    deltaTime: int
    cuePoint: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        cuePoint = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, cuePoint)

@dataclass
class ProgramNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
        return cls(deltaTime, name)

@dataclass
class DeviceNameEvent:
    deltaTime: int
    name: str

    @classmethod
    def fromMemoryMap(cls, deltaTime, length, memoryMap):
        name = struct.unpack(f"{length}s", memoryMap.read(length))[0].decode("ascii")
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
from typing import List
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
    identifier = memoryMap.read(4).decode('ascii')
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
    identifier = memoryMap.read(4).decode('ascii')
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
    tracks: List[MidiTrack]

    @classmethod
    def fromFile(cls, filePath):
        with open(filePath, "rb") as f:
            memoryMap = mmap.mmap(f.fileno(), 0, access = mmap.ACCESS_READ)
            midiFormat, tracksCount, ppqn = parseHeader(memoryMap)
            tracks = parseTracks(memoryMap, tracksCount)
            memoryMap.close()
            return cls(midiFormat, ppqn, tracks)

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
            self.noteOnTable[key] = NoteOnRecord(self.timeInSeconds, event.velocity / 127)

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
    tracks = []
    fileTracks = midiFile.tracks if midiFile.midiFormat != 1 else midiFile.tracks[1:]
    trackIndexUsed = 0
    for trackIndex, track in enumerate(fileTracks):
        notes = []
        notesUsed = []
        trackName = ""
        trackState = TrackState()
        minNote = 1000
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
import json
import time
import math

# write to screen and log
def wLog(toLog):
    print(toLog)
    flog.write(toLog+"\n")

# write to screen and log
def readMTBTrack(id):
    """ Search all infos about a channel in mtb_data
    IN
        id         int     Identifier of channel
    OUT
        jsonTrack
    """
    for chan in jsonData:
        if chan['Channel'] == id:
            return chan
    return None

# Research about a collection
def find_collection(context, item):
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection

# Create collection
def create_collection(collection_name, parent_collection):
    # delete if exist
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
        for ob in collection.objects:
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(collection)
    # create a new one
    new_collection = bpy.data.collections.new(collection_name)
    parent_collection.children.link(new_collection)
    return new_collection

# Create a Cube Mesh
def addCube(collect, name, x, y, z, mat1):
    bpy.ops.mesh.primitive_cube_add()
    oc = bpy.context.active_object
    oc.name = name
    oc.location.x = x * 2.5
    oc.location.y = y * 2.5
    oc.location.z = z * 2.5

    o = bpy.context.object

    # assign to material slots - Both cube and text for union later
    o.data.materials.append(mat1)

    # Little bevel is always a nice idea for a cube
    bpy.ops.object.modifier_add(type="BEVEL")
    bpy.ops.object.modifier_apply(modifier="BEVEL")

    collect_to_unlink = find_collection(bpy.context, o)
    collect.objects.link(o)
    collect_to_unlink.objects.unlink(o)

    return oc

# Affect obj with note event
def eventNote(obj, frameTimeOn, frameTimeOff, velocity):
    eventLenMove = int(fps * 0.1) # Lenght (in frames) before and after event for moving to it, 10% of FPS
    # set initial scale cube before acting
    obj.scale = (1, 1, 1)
    obj.location.z = 0
    obj.keyframe_insert(data_path="scale", frame=frameTimeOn - eventLenMove)  # before upscaling
    obj.keyframe_insert(data_path="location", frame=frameTimeOn - eventLenMove)  
    # Upscale cube at noteNumber on timeOn
    obj.scale = (1, 1, velocity)
    obj.location.z = velocity - 1
    obj.keyframe_insert(data_path="scale", frame=frameTimeOn)  # upscaling
    obj.keyframe_insert(data_path="location", frame=frameTimeOn)
    # set actual scale cube before acting
    obj.scale = (1, 1, velocity)
    obj.location.z = velocity - 1
    obj.keyframe_insert(data_path="scale", frame=frameTimeOff - eventLenMove) # before downscaling
    obj.keyframe_insert(data_path="location", frame=frameTimeOff - eventLenMove)
    # downscale cube at noteNumber on timeOff
    obj.scale = (1, 1, 1)
    obj.location.z = 0
    obj.keyframe_insert(data_path="scale", frame=frameTimeOff)  # downscaling
    obj.keyframe_insert(data_path="location", frame=frameTimeOff)

"""
Main
"""

timeStart = time.time()

# path and name of midi file and so on - temporary => replaced when this become an Blender Extension
path = "W:\\MIDI\\Samples"
filename = "58f441243ff72830e87d849873df926b"

pathMidiFile = path + "\\" + filename + ".mid"
pathAudioFile = path + "\\" + filename + ".mp3"
pathJsonFile = path + "\\" + filename + ".json"
pathLogFile = path + "\\" + filename + ".log"

# Open log file for append
flog = open(pathLogFile, "w+")

# Hope to have 50 fps at min
fps = bCon.scene.render.fps
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
    bCon.scene.sequence_editor.sequences_all[filename + ".mp3"].volume = 0.25
    wLog("Audio file mp3 is loaded into VSE")
else:
    wLog("Audio file mp3 not exist")

# Cube body
matCube = bpy.data.materials.new(name="matCube")
matCube.use_nodes = True
principled = PrincipledBSDFWrapper(matCube, is_readonly=False)
principled.base_color = (0.8, 0.4, 0.2)

newCol = create_collection("MTB", bpy.context.scene.collection)

"""
Create (tracks number) lines of (min/max notes) Cubes
"""

# Determine min and max global for centered objects
noteMaxAllTracks = 0
noteMinAllTracks = 1000
for track in tracks:
    for track in tracks:
        noteMinAllTracks = min( noteMinAllTracks, track.minNote)
        noteMaxAllTracks = max( noteMaxAllTracks, track.maxNote)

noteMidRange = noteMinAllTracks + (noteMaxAllTracks - noteMinAllTracks) / 2
wLog("note min =  " + str(noteMinAllTracks))
wLog("note max =  " + str(noteMaxAllTracks))
wLog("note mid range =  " + str(noteMidRange))

# Create cubes
for track in tracks:
    for note in track.notesUsed:
        cubeName = "Cube-"+str(track.index)+"-"+str(note)
        offsetX = note - noteMidRange
        offsetY = track.index - len(tracks) / 2
        addCube(newCol, cubeName, offsetX, offsetY, 0, matCube)
    wLog("create "+str(len(track.notesUsed))+" cubes for track (range noteMin-noteMax) "+track.name+" ("+str(track.minNote)+"-"+str(track.maxNote)+")")

# Animate cubes accordingly to notes event
maxTimeOff = 0
for track in tracks:
    for note in track.notes:
        maxTimeOff = max(maxTimeOff,note.timeOff)
        # retrieve object by is name
        cubeName = "Cube-"+str(track.index)+"-"+str(note.noteNumber)
        obj = bpy.data.objects[cubeName]
        frameTimeOn = note.timeOn * fps
        frameTimeOff = note.timeOff * fps
        velocity = 8 * note.velocity
        eventNote(obj, frameTimeOn, frameTimeOff, velocity)
    wLog("Animate cubes for track (NbNotes) "+track.name+" ("+str(len(track.notes))+")")

wLog("length of MIDI file in seconds =  " + str(maxTimeOff))
bCon.scene.frame_end = math.ceil(maxTimeOff + 5)*fps

# Close log file
wLog("Script Finished: %.2f sec" % (time.time() - timeStart))
flog.close()
