from config.globals import *
from config.config import bDat, bScn, bCon

# Open log file for append
def initLog(logFile):
    glb.fLog = open(logFile, "w+")

# write to screen and log
def wLog(toLog):
    print(toLog)
    glb.fLog.write(toLog+"\n")
    
# Close logFile
def endLog():
    glb.fLog.close()

import re

"""
    Parses a range string and returns a list of numbers.
    Example input: "1-5,7,10-12"
    Example output: [1, 2, 3, 4, 5, 7, 10, 11, 12]
    return some values calculated from effective range, noteMin, noteMax, octaveCount, effectiveTrackCount
"""
def parseRangeFromTracks(rangeStr):

    def max_gap_values(n, start=0.02, end=1):
        """
        Returns a list of n values between start and end,
        arranged so that the gap between consecutive values is maximized.
        The output list is not in ascending order.
        """
        if n < 1:
            raise ValueError("n must be a positive integer")
        if n == 1:
            return [(start + end) / 2]  # Return the mid value if only one element is needed

        # Generate n equally spaced values between start and end
        step = (end - start) / (n - 1)
        sorted_values = [start + i * step for i in range(n)]

        # Reorder the list to maximize differences between consecutive values
        result = []
        # Start with the middle element
        mid_index = len(sorted_values) // 2
        result.append(sorted_values.pop(mid_index))

        # Alternate: take successivement le plus petit et le plus grand élément restant
        toggle = True
        while sorted_values:
            if toggle:
                result.append(sorted_values.pop(0))
            else:
                result.append(sorted_values.pop(-1))
            toggle = not toggle

        return result

    tracks = glb.tracks
    wLog(f"Track filter used = {rangeStr}")

    numbers = []
    if rangeStr == "*":
        numbers = range(len(tracks))
    else:
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

    # Evaluate noteMin, noteMax and octaveCount from effective range
    noteMin = 1000
    noteMax = 0
    effectiveTrackCount = 0
    tracksSelected = ""
    listOfSelectedTracks = []
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in numbers:
            continue
        
        effectiveTrackCount += 1
        tracksSelected += (f"{trackIndex},")
        listOfSelectedTracks.append(trackIndex)
        noteMin = min(noteMin, track.minNote)
        noteMax = max(noteMax, track.maxNote)

    tracksSelected = tracksSelected[:-1]  # Remove last ,
    wLog(f"Track selected are = {tracksSelected}")

    octaveCount = (noteMax // 12) - (noteMin // 12) + 1

    # Create a table of color
    tracksColor = max_gap_values(effectiveTrackCount, start=0.02, end=1)

    return listOfSelectedTracks, noteMin, noteMax, octaveCount, effectiveTrackCount, tracksColor

# Define color from note number when sharp (black) or flat (white)
def colorFromNoteNumber(noteNumber):
    if noteNumber in [1, 3, 6, 8, 10]:
        return 0.001  # Black note (almost)
    else:
        return 0.01 # White note
    
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
    - baseSaturation: Object property for color saturation
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
    principledBSDF.location = (300, 0)

    attributeBaseColor = nodes.new(type="ShaderNodeAttribute")
    attributeBaseColor.location = (-400, 100)
    attributeBaseColor.attribute_name = "baseColor"
    attributeBaseColor.attribute_type = 'OBJECT'

    attributeBaseSat = nodes.new(type="ShaderNodeAttribute")
    attributeBaseSat.location = (-400, 300)
    attributeBaseSat.attribute_name = "baseSaturation"
    attributeBaseSat.attribute_type = 'OBJECT'

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

    mixColorBase = nodes.new(type='ShaderNodeMixRGB')
    mixColorBase.location = (100, 200)
    mixColorBase.blend_type = 'MIX'
    mixColorBase.inputs[2].default_value = (0.0, 0.0, 0.0, 1)

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
    links.new(colorRampBase.outputs["Color"], mixColorBase.inputs[2])   # Original color
    links.new(attributeBaseSat.outputs["Fac"], mixColorBase.inputs[0])  # Factor from baseSaturation
    links.new(mixColorBase.outputs["Color"], principledBSDF.inputs["Base Color"])  # Output to shader
    links.new(colorRampEmission.outputs["Color"], principledBSDF.inputs["Emission Color"])  # Emission color
    links.new(principledBSDF.outputs["BSDF"], output.inputs["Surface"])  # Output surface

    return mat

# Retrieve octave and noteNumber from note number (0-127)
def extractOctaveAndNote(noteNumber):
    octave = noteNumber // 12
    noteNumber = noteNumber % 12
    return octave, noteNumber

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

# Determine global min/max ranges for scene configuration
def determineGlobalRanges():
    """
    Calculate global note and time ranges across all tracks.
    
    Args:
        tracks: List of MIDI tracks
        
    Returns:
        tuple: (noteMin, noteMax, timeMin, timeMax)
    """
    tracks = glb.tracks
    stats = {
        'noteMin': 1000,
        'noteMax': 0,
        'timeMin': 1000,
        'timeMax': 0,
        'noteMidRange': 0
    }
    
    for track in tracks:
        stats.update({
            'noteMin': min(stats['noteMin'], track.minNote),
            'noteMax': max(stats['noteMax'], track.maxNote),
            'timeMin': min(stats['timeMin'], track.notes[0].timeOn),
            'timeMax': max(stats['timeMax'], track.notes[-1].timeOff)
        })

    # Calculate mid range for centering
    stats['noteMidRange'] = stats['noteMin'] + (stats['noteMax'] - stats['noteMin']) / 2

    wLog(f"Note range: {stats['noteMin']} to {stats['noteMax']} (mid: {stats['noteMidRange']})")
    wLog(f"Time range: {stats['timeMin']:.2f}s to {stats['timeMax']:.2f}s")
    
    return (stats['noteMin'], stats['noteMax'], stats['timeMin'], stats['timeMax'], stats['noteMidRange'])
