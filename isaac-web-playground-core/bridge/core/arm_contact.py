"""Visible rubber fingertips for stable contact with small round props."""
def add_grip_pads(stage, root):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema
    grip=stage.GetPrimAtPath(root+'/gripper')
    if not grip:raise ValueError('SO-101 gripper link missing')
    world=UsdGeom.Xformable(grip).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    material=UsdShade.Material.Define(stage,root+'/GripRubber')
    shader=UsdShade.Shader.Define(stage,root+'/GripRubber/Surface');shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.16,.25,.20))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    physics=UsdPhysics.MaterialAPI.Apply(material.GetPrim());physics.CreateStaticFrictionAttr(2.);physics.CreateDynamicFrictionAttr(1.8);physics.CreateRestitutionAttr(0.)
    for link,x in [('gripper',-.006),('jaw',.010)]:
        parent=stage.GetPrimAtPath(root+'/'+link)
        parent_world=UsdGeom.Xformable(parent).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        pad_world=Gf.Matrix4d(1.);pad_world.SetTranslate(Gf.Vec3d(x,0.,-.084));pad_world=pad_world*world
        pad=UsdGeom.Cube.Define(stage,root+'/'+link+'/GripPad');pad.CreateSizeAttr(1.)
        xf=UsdGeom.Xformable(pad);xf.AddTransformOp().Set(pad_world*parent_world.GetInverse());xf.AddScaleOp().Set(Gf.Vec3f(.004,.026,.032))
        prim=pad.GetPrim();UsdPhysics.CollisionAPI.Apply(prim);PhysxSchema.PhysxCollisionAPI.Apply(prim).CreateContactOffsetAttr(.001)
        binding=UsdShade.MaterialBindingAPI.Apply(prim);binding.Bind(material);binding.Bind(material,materialPurpose='physics')
