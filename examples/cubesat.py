import os
import logging
import numpy as np
import bpy
import pathlib

import kubric as kb
from kubric.renderer import Blender

# --- CLI arguments
parser = kb.ArgumentParser()
parser.set_defaults(
    frame_end=20,
    resolution=(640, 480),
    scratch_dir="cubesat_v2/scratch"
)
FLAGS = parser.parse_args()

# --- Common setups & resources
scene, rng, _, scratch_dir = kb.setup(FLAGS)
renderer = Blender(scene, scratch_dir,
                   samples_per_pixel=64,
                   background_transparency=True)

output_dir = pathlib.Path("./cubesat_v2")

# --- Fetch shapenet
# source_path = os.getenv("SHAPENET_GCP_BUCKET", "gs://kubric-unlisted/assets/ShapeNetCore.v2.json")
# shapenet = kb.AssetSource.from_manifest(source_path)

kubasic = kb.AssetSource.from_manifest("gs://kubric-public/assets/KuBasic/KuBasic.json")

# Add Dome object
dome = kubasic.create(asset_id="dome", name="dome", static=True, background=True)
scene += dome
# Set the texture
dome_blender = dome.linked_objects[renderer]
texture_node = dome_blender.data.materials[0].node_tree.nodes["Image Texture"]
background_hdri_filename = "./panorama_image.png"
texture_node.image = bpy.data.images.load(background_hdri_filename)

# --- Add Klevr-like lights to the scene
scene += kb.assets.utils.get_clevr_lights(rng=rng)
scene.ambient_illumination = kb.Color(0.05, 0.05, 0.05)

# --- Add shadow-catcher floor
# floor = kb.Cube(name="floor", scale=(100, 100, 1), position=(0, 0, -1))
# scene += floor
# Make the floor transparent except for catching shadows
# Together with background_transparency=True (above) this results in
# the background being transparent except for the object shadows.
# if bpy.app.version > (3, 0, 0):
#   floor.linked_objects[renderer].is_shadow_catcher = True
# else:
#   floor.linked_objects[renderer].cycles.is_shadow_catcher = True

# --- Keyframe the camera
scene.camera = kb.PerspectiveCamera(focal_length = 800, sensor_width = 36)
for frame in range(FLAGS.frame_start, FLAGS.frame_end + 1):
  scene.camera.position = kb.sample_point_in_half_sphere_shell(1, 100, 1)
  scene.camera.look_at((0, 0, 0))
  scene.camera.keyframe_insert("position", frame)
  scene.camera.keyframe_insert("quaternion", frame)

# --- Fetch a random (airplane) asset
# airplane_ids = [name for name, spec in shapenet._assets.items()
#                 if spec["metadata"]["category"] == "airplane"]
#
# asset_id = rng.choice(airplane_ids) #< e.g. 02691156_10155655850468db78d106ce0a280f87
# obj = shapenet.create(asset_id=asset_id)
# logging.info(f"selected '{asset_id}'")
obj = kb.FileBasedObject(
  asset_id="cubesat",
  render_filename="cube_sat_v2.obj",
  # bounds=((-1, -1, -1), (1, 1, 1)),
  simulation_filename=None, position=(0, 0, 0))

scene += obj

# --- make object flat on X/Y and not penetrate floor
obj.quaternion = kb.Quaternion(axis=[1, 0, 0], degrees=90)
obj.position = obj.position - (0, 0, obj.aabbox[0][2])
scene.add(obj)

# --- Rendering
logging.info("Rendering the scene ...")
renderer.save_state(output_dir / "scene.blend")
data_stack = renderer.render()

# --- Postprocessing
kb.compute_visibility(data_stack["segmentation"], scene.assets)
data_stack["segmentation"] = kb.adjust_segmentation_idxs(
    data_stack["segmentation"],
    scene.assets,
    [obj]).astype(np.uint8)

kb.file_io.write_rgba_batch(data_stack["rgba"], output_dir)
kb.file_io.write_depth_batch(data_stack["depth"], output_dir)
kb.file_io.write_segmentation_batch(data_stack["segmentation"], output_dir)

# --- Collect metadata
logging.info("Collecting and storing metadata for each object.")
data = {
  "metadata": kb.get_scene_metadata(scene),
  "camera": kb.get_camera_info(scene.camera),
  "object": kb.get_instance_info(scene, [obj])
}
kb.file_io.write_json(filename=output_dir / "metadata.json", data=data)
kb.done()
