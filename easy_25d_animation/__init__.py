# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    "name": "Play2.5D",
    "author": "Zhenjie Zhao",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View",
    "description": "Sketch-based 2.5D Animation Tools",
    "wiki_url": "http://hci.cse.ust.hk/index.html",
    "support": "TESTING",
    "category": "Animation",
}


if "bpy" in locals():
    import importlib
    importlib.reload(utils)
    importlib.reload(ui_utils)
    importlib.reload(ops_utils)
    importlib.reload(mesh)
else:
    from . import utils, ui_utils, ops_utils, mesh

import os
import sys
import math
import mathutils
import bpy
import bpy.utils.previews
import bmesh
from rna_prop_ui import PropertyPanel
from bpy.app.handlers import persistent
from bpy.types import (Panel, Operator, PropertyGroup, UIList, Menu)
from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       EnumProperty,
                       PointerProperty)

# depends on sklean
import numpy as np
from numpy import linalg as LA
from sklearn.decomposition import PCA

################################################################################
# Global
################################################################################

class MySettings(PropertyGroup):
    instance_nb = 6
    enum_mode = EnumProperty(name='Mode',
                             description='Different drawing mode',
                             items=[('IMPORT_MODE','Import',''),
                                    ('CONSTRUCTING_MODE','Construction',''),
                                    ('ANIMATION_MODE','Animation','')],
                             default='IMPORT_MODE')

class MySettingOperatorPlay(bpy.types.Operator):
    bl_idname = 'mysetting.play'
    bl_label = 'MySetting Play'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        scene = context.scene
        scene.frame_start = AnimationProperty.current_frame
        scene.frame_end = AnimationProperty.current_frame+AnimationProperty.frame_block_nb-1

        bpy.ops.screen.animation_play()
        if context.screen.is_animation_playing==False:
            scene.frame_current = AnimationProperty.current_frame

        return {'FINISHED'}


class MySettingOperatorReset(bpy.types.Operator):
    bl_idname = 'mysetting.reset'
    bl_label = 'MySetting Reset'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        bpy.ops.wm.read_homefile()
        bpy.ops.wm.addon_refresh()
        return {'FINISHED'}

class MySettingOperatorRender(bpy.types.Operator):
    bl_idname = 'mysetting.render'
    bl_label = 'MySetting Render'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        scene = context.scene
        scene.frame_start = 1
        scene.frame_end = 20 #AnimationProperty.current_frame+AnimationProperty.frame_block_nb-1

        bpy.ops.render.render(animation=True)
        return {'FINISHED'}

################################################################################
# Construction
################################################################################

# Property
class ConstructionProperty:
    instance_nb = 6

# Operator
class ConstructionOperatorInstancing(bpy.types.Operator):
    bl_idname = "construction.instancing"
    bl_label = "Instancing based on strokes"
    bl_options = {"UNDO"}

    small_depth = 0

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil != None) and (context.active_object!=None)

    def invoke(self, context, event):
        # import pdb; pdb.set_trace()
        gp = context.scene.grease_pencil
        strokes = gp.layers.active.active_frame.strokes

        try:
            stroke = strokes[-1]
        except IndexError:
            pass
        else:
            verts = []
            points = stroke.points
            for i in range(len(stroke.points)):
                verts.append(points[i].co)

            sampling_nb = min(ConstructionProperty.instance_nb, len(verts))
            sampling_step = len(verts)/sampling_nb

            shift = []
            for i in range(sampling_nb):
                idx = int(i*sampling_step)
                if idx<len(verts):
                    x = verts[idx].x
                    y = verts[idx].y
                    z = verts[idx].z
                    shift.append((x,y,z))

            # instancing (including animation data)
            model_obj = context.active_object

            # make some flags
            is_copy_animation = (model_obj.animation_data!=None)
            is_projection = context.scene.is_projection

            if is_copy_animation:
                model_fcurve_x = model_obj.animation_data.action.fcurves[0]
                model_fcurve_z = model_obj.animation_data.action.fcurves[1]
                N = len(model_fcurve_x.keyframe_points)

            for i in range(sampling_nb):
                new_obj = model_obj.copy()
                new_obj.data = model_obj.data.copy()

                if is_projection:
                    new_obj.location[1] = model_obj.location[1] + i*shift[i][2] # z denotes depth
                else:
                    new_obj.location[1] = model_obj.location[1] + ConstructionOperatorInstancing.small_depth

                if is_copy_animation:
                    new_obj.animation_data_create()
                    new_obj.animation_data.action = bpy.data.actions.new(name="LocationAnimation")

                    fcurve_x = new_obj.animation_data.action.fcurves.new(data_path='location', index=0)
                    fcurve_z = new_obj.animation_data.action.fcurves.new(data_path='location', index=2)

                    x_pre = 0
                    z_pre = 0

                    for k in range(N):
                        frame_idx = model_fcurve_x.keyframe_points[k].co[0] # (frame index, real f-value)
                        if k==0:
                            x_cur = shift[i][0]
                            z_cur = shift[i][2]
                        else:
                            x_cur = model_fcurve_x.keyframe_points[k].co[1]+x_pre2-x_pre
                            z_cur = model_fcurve_z.keyframe_points[k].co[1]+z_pre2-z_pre
                        fcurve_x.keyframe_points.insert(frame_idx, x_cur, {'FAST'})
                        fcurve_z.keyframe_points.insert(frame_idx, z_cur, {'FAST'})

                        x_pre = model_fcurve_x.keyframe_points[k].co[1]
                        z_pre = model_fcurve_z.keyframe_points[k].co[1]

                        x_pre2 = x_cur
                        z_pre2 = z_cur
                else:
                    if is_projection:
                        new_obj.location[0] = shift[0][0]
                        new_obj.location[2] = shift[0][2]
                    else:
                        new_obj.location[0] = shift[i][0]
                        new_obj.location[2] = shift[i][2]


                context.scene.objects.link(new_obj)
                ConstructionOperatorInstancing.small_depth += 0.001 # prevent z shadowing

            bpy.ops.object.select_all(action='DESELECT')
        return {'FINISHED'}

class CleanStrokes(bpy.types.Operator):
    bl_idname = 'layout.cleanstrokes'
    bl_label = 'Cleaning strokes'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil != None) #and (context.scene.grease_pencil.layers.active.active_frame.strokes[-1]!=None)

    def invoke(self, context, event):
        g = context.scene.grease_pencil
        for l in g.layers:
            g.layers.remove(l)
        return {'FINISHED'}

################################################################################
# Animation
################################################################################

# Property
class AnimationProperty():
    current_frame = 1
    frame_block_nb = 100
    sampling_step = 2

# UI

# Operator
class AnimationOperatorUpdate(bpy.types.Operator):
    bl_idname = 'animation.animation_update'
    bl_label = 'Animation Update'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None)

    def invoke(self, context, event):
        # import pdb; pdb.set_trace()

        obj = context.active_object
        if context.scene.enum_brushes=='FOLLOWPATH':
            strokes = AnimationBrushes.brush_dict['FOLLOWPATH'].active_frame.strokes
            try:
                stroke = strokes[-1]
            except IndexError:
                pass
            else:
                obj.animation_data_create()
                obj.animation_data.action = bpy.data.actions.new(name="LocationAnimation")

                N = len(stroke.points)

                fcurve_x = obj.animation_data.action.fcurves.new(data_path='location', index=0)
                fcurve_z = obj.animation_data.action.fcurves.new(data_path='location', index=2)

                i = 0
                while int(i*AnimationProperty.sampling_step) < N:
                    idx = int(i*AnimationProperty.sampling_step)
                    position = stroke.points[idx].co
                    fcurve_x.keyframe_points.insert(AnimationProperty.current_frame+idx, position[0], {'FAST'})
                    fcurve_z.keyframe_points.insert(AnimationProperty.current_frame+idx, position[2], {'FAST'})
                    i+=1

        elif context.scene.enum_brushes=='HPOINT':
            mesh = obj.data
            mesh.animation_data_create()
            action = bpy.data.actions.new(name='MeshAnimation')
            mesh.animation_data.action = action

            # Point handler
            pca = PCA(n_components=2)
            strokes = AnimationBrushes.brush_dict['HPOINT'].active_frame.strokes
            stroke = strokes[-1]

            phandler = stroke.points[0].co.xyz
            ppath = [p.co.xz for p in stroke.points]
            phandler = np.array(phandler)
            ppath = np.array(ppath) # the size is correct, amazing

            #PCA
            res = pca.fit(ppath).transform(ppath)
            res[:,1] = 0.0
            new_ppath = pca.inverse_transform(res)
            new_phandler = phandler

            # proportional based linear blend skinning
            (nframe, ndim) = new_ppath.shape
            delta_list = []
            for i in range(1, nframe):
                t0 = new_ppath[i, 0] - new_ppath[i-1, 0]
                t1 = new_ppath[i, 1] - new_ppath[i-1, 1]
                delta_list.append((t0, t1))

            weight = {}
            matrix_world = obj.matrix_world
            for vert in mesh.vertices:
                v_co_world = np.array(matrix_world*vert.co)
                dist = LA.norm(v_co_world-new_phandler, 2)
                weight[vert.index] = np.exp(-dist)

            normalized_delta_list = []
            for i in range(AnimationProperty.frame_block_nb):
                normalized_delta_list.append(delta_list[i%len(delta_list)])

            frames = [AnimationProperty.current_frame+i for i in range(AnimationProperty.frame_block_nb)]

            for vert in mesh.vertices:
                fcurve_x = action.fcurves.new('vertices[%d].co'%vert.index, index=0)
                fcurve_y = action.fcurves.new('vertices[%d].co'%vert.index, index=1)
                co_kf_x = vert.co[0]
                co_kf_y = vert.co[1]
                for frame, val in zip(frames, normalized_delta_list):
                    co_kf_x += weight[vert.index]*val[0]
                    co_kf_y += weight[vert.index]*val[1]
                    fcurve_x.keyframe_points.insert(frame, co_kf_x, {'FAST'})
                    fcurve_y.keyframe_points.insert(frame, co_kf_y, {'FAST'})

        return {'FINISHED'}

# Handler
class AnimationBrushes:
    gp = None
    brush_dict = {}

def AnimationHandlerUpdateBrushes(self, context):
    if AnimationBrushes.gp == None:
        AnimationBrushes.gp = bpy.data.grease_pencil.new('AnimationPencil')

    gp = AnimationBrushes.gp
    context.scene.grease_pencil = gp

    if 'FOLLOWPATH' not in AnimationBrushes.brush_dict:
        layer = gp.layers.new('FOLLOWPATH')
        layer.tint_color = (1.0, 0.0, 0.0)
        layer.tint_factor = 1.0
        AnimationBrushes.brush_dict['FOLLOWPATH'] = layer
    if 'HPOINT' not in AnimationBrushes.brush_dict:
        layer = gp.layers.new('HPOINT')
        layer.tint_color = (0.5, 0.5, 0.5)
        layer.tint_factor = 1.0
        AnimationBrushes.brush_dict['HPOINT'] = layer

    if context.scene.enum_brushes!=None:
        gp.layers.active = AnimationBrushes.brush_dict[context.scene.enum_brushes]

    return None

################################################################################
# Recording
################################################################################

class RecordingData:
    start_frame = []
    end_frame = []
    camera_fcurve_x = None
    camera_fcurve_y = None

# Property
class RecordingPropertyItem(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty(name='Name', default='')
    index = bpy.props.IntProperty(name='Index', default=0)
    start_frame = bpy.props.IntProperty(name='Startframe', default=0)
    end_frame = bpy.props.IntProperty(name='Endframe', default=0)

# UI
class RecordingUIListItem(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(0.3)
        split.prop(item, "name", text="", emboss=False, icon='CLIP')
        split.label('Start: %d' % RecordingData.start_frame[index])
        split.label('End: %d' % RecordingData.end_frame[index])

# Operator
# https://blender.stackexchange.com/questions/30444/create-an-interface-which-is-similar-to-the-material-list-box
class RecordingOperatorListAction(bpy.types.Operator):
    bl_idname = 'recording.list_action'
    bl_label = 'List Action'

    def invoke(self, context, event):
        scene = context.scene

        item = scene.recording_array.add()
        item.id = len(scene.recording_array)
        item.name = 'Recording-%d'%len(scene.recording_array)
        item.index = len(scene.recording_array)
        scene.recording_index = (len(scene.recording_array)-1)

        # add camera animation
        obj = bpy.data.objects['Camera']
        if obj.animation_data==None:
            obj.animation_data_create()
            obj.animation_data.action = bpy.data.actions.new(name='LocationAnimation')
            RecordingData.camera_fcurve_x = obj.animation_data.action.fcurves.new(data_path='location', index=0)
            RecordingData.camera_fcurve_y = obj.animation_data.action.fcurves.new(data_path='location', index=1)

        position = obj.location
        RecordingData.camera_fcurve_x.keyframe_points.insert(AnimationProperty.current_frame, position[0], {'FAST'})
        RecordingData.camera_fcurve_y.keyframe_points.insert(AnimationProperty.current_frame, position[1], {'FAST'})

        RecordingData.start_frame.append(AnimationProperty.current_frame)
        RecordingData.end_frame.append(AnimationProperty.current_frame+AnimationProperty.frame_block_nb-1)
        AnimationProperty.current_frame+=AnimationProperty.frame_block_nb

        return {"FINISHED"}

################################################################################
# Camera
################################################################################

# Operator
class CameraOperatorSetting(bpy.types.Operator):
    bl_idname = 'camera.setting'
    bl_label = 'Camera Setting'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        context.scene.cursor_location.x = context.scene.objects['Camera'].location.x
        context.scene.cursor_location.y = context.scene.objects['Camera'].location.y+2.5
        return {'FINISHED'}

# UI
class CameraUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_camera_path'
    bl_label = 'Camera Path'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout
        camera = context.scene.objects['Camera']
        assert(camera!=None)

        box = layout.box()
        box.prop(camera, 'location', text='LF/RT', index=0)
        box.prop(camera, 'location', text='FWD/BWD', index=1)
        box.separator()
        box.operator('camera.setting', text='Set', icon='RENDER_STILL')

################################################################################
# Main UI:
################################################################################

class MainUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_2.5d_animation'
    bl_label = 'Animation'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label('Mode')
        my_settings = scene.my_settings
        box.prop(my_settings, 'enum_mode', text='')

        if my_settings.enum_mode == 'IMPORT_MODE':
            column = box.column()
            column.operator('import_image.to_grid', text='Import', icon='FILE_FOLDER')

        elif my_settings.enum_mode == 'CONSTRUCTING_MODE':
            column = box.column()
            column.prop(context.scene, 'is_projection')
            column.operator('construction.instancing', text='Instancing', icon='BOIDS')
            column.separator()
            column.operator('layout.cleanstrokes', text='Clean Strokes', icon='MESH_CAPSULE')

        elif my_settings.enum_mode == 'ANIMATION_MODE':
            column = box.column()
            column.prop(context.scene, 'enum_brushes', text='Brushes')
            column.separator()
            column.operator('animation.animation_update', text='Update', icon='ANIM')
            column.separator()
            column.operator('layout.cleanstrokes', text='Clean Strokes', icon='MESH_CAPSULE')

        for i in range(3):
            layout.split()

        box = layout.box()
        box.label('Tools')
        col = box.column()
        row=col.row(align=True)
        row.operator('gpencil.draw', text='Draw', icon='BRUSH_DATA').mode='DRAW'
        row.operator('transform.resize', text='Scale', icon='VIEWZOOM')
        row=col.row(align=True)
        row.operator('ed.undo', text='Undo', icon='BACK')
        row.operator('ed.redo', text='Redo', icon='FORWARD')
        if context.screen.is_animation_playing==True:
            col.operator("mysetting.play", text="Pause", icon='PAUSE')
        else:
            col.operator('mysetting.play', text='Preview', icon='RIGHTARROW')
        col.operator('mysetting.reset', text='Reset', icon='HAND')

        for i in range(3):
            layout.split()

        box = layout.box()
        box.label('Record')
        row = box.row()
        col = row.column()
        col.template_list('RecordingUIListItem', '', scene, 'recording_array', scene, 'recording_index', rows=2)

        col = box.column()
        col.operator('recording.list_action', icon='ZOOMIN', text='Add')

class RenderingUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_rendering'
    bl_label = 'Rendering'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout
        # scene = context.scene
        rd = context.scene.render
        # image_settings = rd.image_settings
        # file_format = image_settings.file_format

        box = layout.box()
        # box.label('Render VR Video')
        col = box.column()
        col.operator('mysetting.render', text='Rendering', icon='COLORSET_03_VEC')
        col.separator()
        col.prop(rd, "filepath", text="")
################################################################################
# Logic:
################################################################################

def register():
    bpy.utils.register_module(__name__)

    bpy.types.Scene.my_settings = PointerProperty(type=MySettings)

    # Construction
    bpy.types.Scene.is_projection = bpy.props.BoolProperty(name='Projection')

    # Animation
    bpy.types.Scene.enum_brushes = EnumProperty(name='Brushes',
                                                description='Different Brushes',
                                                items=[('', "", ""),
                                                       ('FOLLOWPATH','Follow Path',''),
                                                       # ('ANCHOR', "Anchor", ""), ('RIGID', "Rigid", ""),
                                                       ('HPOINT','Handle Point','')],
                                                default='',
                                                update=AnimationHandlerUpdateBrushes)

    # Recording
    bpy.types.Scene.recording_array = bpy.props.CollectionProperty(type=RecordingPropertyItem)
    bpy.types.Scene.recording_index = bpy.props.IntProperty()

def unregister():
    bpy.utils.unregister_module(__name__)

    del bpy.types.Scene.my_settings

    # Recording
    del bpy.types.Scene.recording_array
    del bpy.types.Scene.recording_index

if __name__ == "__main__" :
    register()
