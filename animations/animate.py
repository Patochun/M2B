from animations.barGraph import createBlenderBGAnimation
from animations.stripNotes import createStripNotes
from animations.waterFall import createWaterFall
from animations.fireworksV1 import createFireworksV1
from animations.fireworksV2 import createFireworksV2
from animations.fountain import createFountain
from animations.lightShow import createLightShow

def animate(animation, track_mask, animation_type):
    if animation == "barGraph":
        createBlenderBGAnimation(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "stripNotes":
        createStripNotes(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "waterFall":
        createWaterFall(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "fireworksV1":
        createFireworksV1(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "fireworksV2":
        createFireworksV2(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "fountain":
        createFountain(trackMask=track_mask, typeAnim=animation_type)
    elif animation == "lightShow":
        createLightShow(trackMask=track_mask, typeAnim=animation_type)
    else:
        print("Invalid animation type")
