"""
Global state manager for M2B application using a singleton pattern.
Provides centralized access to shared variables across all modules.
"""

class globalState:
    """Singleton class to manage global state across M2B modules"""
    
    def __init__(self):
        self._tracks = None
        self._matGlobalCustom = None
        self._masterCollection = None
        self._masterLocCollection = None
        self._hiddenCollection = None
        self._lastNoteTimeOff = None
        self._fps = None
        self._fLog = None

    @property
    def tracks(self):
        return self._tracks

    @tracks.setter
    def tracks(self, value):
        self._tracks = value

    @property
    def matGlobalCustom(self):
        return self._matGlobalCustom

    @matGlobalCustom.setter
    def matGlobalCustom(self, value):
        self._matGlobalCustom = value

    @property
    def masterCollection(self):
        return self._masterCollection

    @masterCollection.setter
    def masterCollection(self, value):
        self._masterCollection = value

    @property
    def lastNoteTimeOff(self):
        return self._lastNoteTimeOff

    @lastNoteTimeOff.setter
    def lastNoteTimeOff(self, value):
        self._lastNoteTimeOff = value

    @property
    def fps(self):
        return self._fps

    @fps.setter
    def fps(self, value):
        self._fps = value

    @property
    def fLog(self):
        return self._fLog

    @fLog.setter 
    def fLog(self, value):
        self._fLog = value

# Single global instance
glb = globalState()

# Export all properties through this instance
__all__ = ['glb']

