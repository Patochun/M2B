from config.globals import *
from config.config import bCon, bOps, bDat, bTyp, BlenderObjectType
from utils.collection import moveToCollection
from math import atan2
import bmesh

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
    obj["baseSaturation"] = 1.0  # Base saturation as a float
    obj.id_properties_ui("baseSaturation").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Saturation factor for base Color (0 to 1)"
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
    obj["noteStatus"] = 0.0  # Status of note as a float
    obj.id_properties_ui("noteStatus").update(
        min=0.0,  # Minimum value
        max=1.0,  # Maximum value
        step=0.01,  # Step size for the slider
        description="Mean if note Off = 0.0 else = velocity"
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
    resolution: int=12,
    # UVSPHERE
    segments: int=24,
    rings: int=24,
    # LIGHTSHOW
    typeLight: str='POINT'
    ) -> bTyp.Object:
    
    match objectType:
        case BlenderObjectType.PLANE:
            bOps.mesh.primitive_plane_add(size=1, location=location)
            obj = bCon.active_object
            obj.scale = (width, height, 1)
            
        case BlenderObjectType.ICOSPHERE:
            bOps.mesh.primitive_ico_sphere_add(radius=radius, location=location)
            obj = bCon.active_object
            
        # Create a UV Sphere with re-ordered vertices from 0 at north pole
        # from top to bottom in each ring
        # clockwise for each ring
        case BlenderObjectType.UVSPHERE:

            # Create a temporary UV Sphere
            bOps.mesh.primitive_uv_sphere_add(
                radius=radius, 
                location=location,
                segments=segments,
                ring_count=rings
            )
            tempObj = bCon.active_object
            tempObj.name = "UVSphereTemp"
            tempMesh = tempObj.data

            # Switch to edit mode to manipulate topology
            bOps.object.mode_set(mode='EDIT')
            bm = bmesh.from_edit_mesh(tempMesh)

            # Store original vertices and their positions
            originalVertices = list(bm.verts)

            # 1. Find the highest vertex (North Pole)
            poleNorth = max(originalVertices, key=lambda v: v.co.z)
            sortedVerts = [poleNorth]

            # 2. Sort the rings from top to bottom (excluding poles)
            uniqueZValues = sorted(set(v.co.z for v in originalVertices), reverse=True)[1:-1]

            for z in uniqueZValues:
                ringVerts = [v for v in originalVertices if v.co.z == z]

                # Correctly sort vertices in each ring based on polar angle around Z
                ringVerts.sort(key=lambda v: atan2(v.co.y, v.co.x))
                
                sortedVerts.extend(ringVerts)

            # 3. Find the lowest vertex (South Pole)
            poleSouth = min(originalVertices, key=lambda v: v.co.z)
            sortedVerts.append(poleSouth)

            # 4. Create a NEW mesh with sorted vertices
            newMesh = bDat.meshes.new("UVSphereReordered")
            obj = bDat.objects.new("UVSphereReordered", newMesh)
            bCon.collection.objects.link(obj)

            # Convert sorted vertices into a list of positions
            newVertices = [v.co for v in sortedVerts]

            # Reconstruct faces using original topology
            oldFaces = [[originalVertices.index(v) for v in f.verts] for f in bm.faces]
            newFaces = [[sortedVerts.index(originalVertices[idx]) for idx in face] for face in oldFaces]

            # Add data to the new mesh
            newMesh.from_pydata(newVertices, [], newFaces)
            newMesh.update()

            # Remove the old object
            bDat.objects.remove(tempObj)

            # Select the new object
            bCon.view_layer.objects.active = obj
            # obj.select_set(True)
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
            
        case BlenderObjectType.POINT:
            bOps.object.light_add(type=typeLight, location=location)
            obj = bCon.active_object

            # Get the Light data
            objData = obj.data
            objData.energy = 20000
            objData.shadow_soft_size = radius  # Radius of the light source
            objData.color = (1.0,1.0,1.0)

        case BlenderObjectType.LIGHTSHOW:
            bOps.object.light_add(type=typeLight, location=location)
            obj = bCon.active_object

            # Get the Light data
            objData = obj.data
            objData.energy = 1
            objData.shadow_soft_size = radius  # Radius of the light source
            objData.color = (1.0,1.0,1.0)
            objData.use_nodes = True  # Enable shader nodes

            # Access the node tree
            nodeTree = objData.node_tree
            nodes = nodeTree.nodes
            links = nodeTree.links

            # Remove existing nodes
            for node in nodes:
                nodes.remove(node)

            # Add ColorRamp Emission node
            colorRampEmission = nodes.new(type="ShaderNodeValToRGB")
            colorRampEmission.location = (-400, 0)
            colorRampEmission.color_ramp.color_mode = 'HSV'
            colorRampEmission.color_ramp.interpolation = 'CARDINAL'  # Ensure cardinal interpolation
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

            # Add Texture Coordinate node before Voronoi
            texCoord = nodes.new(type='ShaderNodeTexCoord')
            texCoord.location = (-800, -200)  # Position before Voronoi

            # Add Voronoi Texture node
            voronoiTexture = nodes.new(type='ShaderNodeTexVoronoi')
            voronoiTexture.location = (-600, -200)  # Position before ColorRampTexture
            voronoiTexture.inputs['Scale'].default_value = 10
            # voronoiTexture.inputs['W'].default_value = 0
            voronoiTexture.inputs['Roughness'].default_value = 0
            voronoiTexture.inputs['Randomness'].default_value = 0

            # Add ColorRamp Texture node
            colorRampTexture = nodes.new(type="ShaderNodeValToRGB")
            colorRampTexture.location = (-400, -200)
            colorRampTexture.color_ramp.color_mode = 'RGB'
            colorRampTexture.color_ramp.interpolation = 'LINEAR'  # Ensure linear interpolation
            colorRampTexture.color_ramp.elements[0].position = 0.4  # Black
            colorRampTexture.color_ramp.elements[0].color = (0, 0, 0, 1)
            colorRampTexture.color_ramp.elements[1].position = 0.5  # White
            colorRampTexture.color_ramp.elements[1].color = (1, 1, 1, 1)

            # Add Mix Color node
            mixColor = nodes.new(type='ShaderNodeMixRGB')
            mixColor.location = (-100, -100)  # Position between the two ColorRamps
            mixColor.blend_type = 'DIVIDE'
            mixColor.inputs[0].default_value = 0.5  # Set mix factor to 0.5            

            # Add Emission node
            emissionNode = nodes.new(type="ShaderNodeEmission")
            emissionNode.location = (100, 0)

            # Add Output Light node
            outputNode = nodes.new(type="ShaderNodeOutputLight")
            outputNode.location = (300, 0)

            # Link nodes
            links.new(colorRampEmission.outputs[0], mixColor.inputs[1])
            links.new(texCoord.outputs["Normal"], voronoiTexture.inputs["Vector"])
            links.new(voronoiTexture.outputs[0], colorRampTexture.inputs[0])
            links.new(colorRampTexture.outputs[0], mixColor.inputs[2])
            links.new(mixColor.outputs[0], emissionNode.inputs["Color"])  # Connect Mix to Emission color
            links.new(emissionNode.outputs["Emission"], outputNode.inputs["Surface"])  # Emission → Output

            # Add driver for emission strength
            driver = emissionNode.inputs["Strength"].driver_add("default_value").driver
            driver.type = 'SCRIPTED'
            
            # Add variable for emission strength
            var = driver.variables.new()
            var.name = "emissionStrength"
            var.type = 'SINGLE_PROP'
            var.targets[0].id = obj  # Reference to light object
            var.targets[0].data_path = '["emissionStrength"]'
            
            # Set driver expression
            driver.expression = "emissionStrength"

            # Add driver for ColorRamp fac input
            driver = colorRampEmission.inputs[0].driver_add('default_value').driver
            driver.type = 'SCRIPTED'
            
            # Add variable for emission color
            var = driver.variables.new()
            var.name = "emissionColor"
            var.type = 'SINGLE_PROP'
            var.targets[0].id = obj
            var.targets[0].data_path = '["emissionColor"]'
            
            # Set driver expression
            driver.expression = "emissionColor"
            
        case BlenderObjectType.EMPTY:
            bOps.object.empty_add(type='PLAIN_AXES', location=location)
            obj = bCon.active_object
            obj.name = name
            obj.empty_display_size = 2.0
            obj.empty_display_type = 'PLAIN_AXES'

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
# Independant = True : Create a new object with new mesh
# Independant = False : Create a new object with same mesh
def createDuplicateLinkedObject(collection, originalObject, name, independant=False):
    if independant:
        linkedObject = originalObject.copy()
        linkedObject.data = originalObject.data.copy()
        linkedObject.animation_data_clear()
        linkedObject.name = name
    else:
        linkedObject = originalObject.copy()
        linkedObject.name = name

    collection.objects.link(linkedObject)
    # Get collection name and find matching empty in masterLocCollection
    if glb.masterLocCollection and collection.name+"_MasterLocation" in glb.masterLocCollection.objects:
        parentEmpty = glb.masterLocCollection.objects[collection.name+"_MasterLocation"]
        linkedObject.parent = parentEmpty
    return linkedObject

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

def initMaterials():

    # Create global material
    glb.matGlobalCustom = CreateMatGlobalCustom()
