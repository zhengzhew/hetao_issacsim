"""Robot adapters: the common interface plus one implementation per drive type."""
from __future__ import annotations

from .app_context import Usd, enable_extension, kit, math, np, omni
from .catalog import asset_url
from .scene import robot_spawn
from .uploads import _json_safe
from .compat import duck_policy_driven


def apply_contact_friction(prim_path: str, friction: float) -> int:
    """Give the robot's own colliders friction, rather than trusting the floor.

    A scene's ground is authored for whatever that scene was built for, not
    for whatever gets spawned into it later. PhysX combines the two
    materials, so raising the robot's side works whatever it is standing on,
    and modifies no scene.

    The binding goes on the root. Walking the descendants and binding each
    collider individually finds nothing on an instanced asset -- its geometry
    is instanced, and Usd.PrimRange does not enter instance prototypes by
    default. Material bindings inherit down the namespace, so one binding at
    the top reaches everything including the instanced parts.
    """
    try:
        from pxr import Usd, UsdPhysics, UsdShade
        stage = omni.usd.get_context().get_stage()
        root = stage.GetPrimAtPath(prim_path)
        if not root or not root.IsValid():
            print(f"[stage2] contact friction: no prim at {prim_path}", flush=True)
            return 0
        material_path = "/World/RobotContactMaterial"
        material = UsdShade.Material.Define(stage, material_path)
        api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        api.CreateStaticFrictionAttr().Set(float(friction))
        api.CreateDynamicFrictionAttr().Set(float(friction))
        api.CreateRestitutionAttr().Set(0.0)
        UsdShade.MaterialBindingAPI.Apply(root).Bind(
            material, UsdShade.Tokens.weakerThanDescendants, "physics")
        colliders = sum(
            1 for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies())
            if prim.HasAPI(UsdPhysics.CollisionAPI))
        print(f"[stage2] contact friction {friction} bound at {prim_path} "
              f"({colliders} collider(s) beneath it)", flush=True)
        return colliders
    except Exception as exc:
        print(f"[stage2] could not set contact friction: {type(exc).__name__}: {exc}", flush=True)
        return 0


class RobotAdapter:
    adapter_name = "none"

    def info(self) -> dict:
        return {"configured": False, "ready": False, "adapter": self.adapter_name, "capabilities": {}}

    def apply_motion(self, linear: float, lateral: float, angular: float) -> dict:
        return {"accepted": False, "reason": "robot adapter not configured"}

    def stop(self) -> None:
        pass

    def pose(self) -> dict | None:
        return None

    def reset(self) -> dict:
        return {"reset": False, "reason": "robot adapter not configured"}


class WheeledAdapterBase(RobotAdapter):
    def __init__(self, config: dict, scene: dict):
        self.config = dict(config)
        self.scene = dict(scene)
        self.robot = None
        self.controller = None
        self.api = "unknown"
        self.ready = False
        self.initial_pose = None

    def _common_info(self) -> dict:
        return {
            "configured": True,
            "ready": self.ready,
            "id": self.config["id"],
            "name": self.config["name"],
            "adapter": self.adapter_name,
            "api": self.api,
            "prim_path": self.config["prim_path"],
            "wheel_dof_names": self.config["wheel_dof_names"],
            "max_linear_speed": float(self.config.get("max_linear_speed", 0.5)),
            "max_lateral_speed": float(self.config.get("max_lateral_speed", 0.0)),
            "max_angular_speed": float(self.config.get("max_angular_speed", 1.5)),
        }

    def pose(self) -> dict | None:
        if self.robot is None:
            return None
        if self.api.startswith("isaacsim.robot.experimental"):
            positions, orientations = self.robot.get_world_poses()
            p = np.asarray(positions)[0].tolist()
            q = np.asarray(orientations)[0].tolist()
        else:
            position, orientation = self.robot.get_world_pose()
            p = np.asarray(position).tolist()
            q = np.asarray(orientation).tolist()
        return _json_safe({"position": p, "orientation_wxyz": q})

    def reset(self) -> dict:
        self.stop()
        if self.initial_pose is None:
            return {"reset": False, "reason": "initial pose unavailable"}
        p = np.asarray(self.initial_pose["position"], dtype=np.float32)
        q = np.asarray(self.initial_pose["orientation_wxyz"], dtype=np.float32)
        if self.api.startswith("isaacsim.robot.experimental"):
            self.robot.set_world_poses(positions=p.reshape(1, 3), orientations=q.reshape(1, 4))
        else:
            self.robot.set_world_pose(position=p, orientation=q)
        for _ in range(4):
            kit.update()
        return {"reset": True, "pose": self.pose()}

    def _finish_init(self) -> None:
        timeline = omni.timeline.get_timeline_interface()
        if not timeline.is_playing():
            timeline.play()
        for _ in range(30):
            kit.update()
        try:
            if hasattr(self.robot, "initialize"):
                self.robot.initialize()
        except Exception:
            pass
        for _ in range(10):
            kit.update()
        self.ready = True
        self.initial_pose = self.pose()
        print(f"[stage2] robot ready id={self.config['id']} adapter={self.adapter_name} api={self.api}", flush=True)


class DifferentialDriveAdapter(WheeledAdapterBase):
    adapter_name = "differential-drive"

    def __init__(self, config: dict, scene: dict):
        super().__init__(config, scene)
        self._initialize()

    def _initialize(self) -> None:
        prim_path = str(self.config["prim_path"])
        wheel_names = list(self.config["wheel_dof_names"])
        spawn = np.asarray(robot_spawn(self.scene, self.config), dtype=np.float32)
        usd_path = asset_url(self.config["asset_path"])
        radius = float(self.config["wheel_radius"])
        base = float(self.config["wheel_base"])
        max_linear = float(self.config.get("max_linear_speed", 0.5))
        max_angular = float(self.config.get("max_angular_speed", 1.5))
        max_wheel = float(self.config.get("max_wheel_speed", 30.0))

        try:
            enable_extension("isaacsim.robot.experimental.wheeled_robots")
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.robot.experimental.wheeled_robots.controllers import DifferentialController
            from isaacsim.robot.experimental.wheeled_robots.robots import WheeledRobot

            self.robot = WheeledRobot(paths=prim_path, wheel_dof_names=wheel_names, usd_path=usd_path, positions=spawn.tolist())
            self.controller = DifferentialController(
                wheel_radius=radius,
                wheel_base=base,
                max_linear_speed=max_linear,
                max_angular_speed=max_angular,
                max_wheel_speed=max_wheel,
            )
            SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cpu")
            try:
                scenes = SimulationManager.get_physics_scenes()
                if scenes:
                    scenes[0].set_enabled_gpu_dynamics(False)
            except Exception:
                pass
            self.api = "isaacsim.robot.experimental.wheeled_robots"
        except (ImportError, ModuleNotFoundError):
            enable_extension("isaacsim.robot.wheeled_robots")
            from isaacsim.robot.wheeled_robots.controllers import DifferentialController
            from isaacsim.robot.wheeled_robots.robots import WheeledRobot

            self.robot = WheeledRobot(
                prim_path=prim_path,
                name=f"web_{self.config['id']}",
                wheel_dof_names=wheel_names,
                create_robot=True,
                usd_path=usd_path,
                position=spawn,
            )
            self.controller = DifferentialController(
                name=f"web_diff_{self.config['id']}",
                wheel_radius=radius,
                wheel_base=base,
                max_linear_speed=max_linear,
                max_angular_speed=max_angular,
                max_wheel_speed=max_wheel,
            )
            self.api = "isaacsim.robot.wheeled_robots"
        self._finish_init()

    def info(self) -> dict:
        return {
            **self._common_info(),
            "wheel_radius": float(self.config["wheel_radius"]),
            "wheel_base": float(self.config["wheel_base"]),
            "capabilities": {"forward": True, "lateral": False, "yaw": True},
        }

    def apply_motion(self, linear: float, lateral: float, angular: float) -> dict:
        if not self.ready:
            return {"accepted": False, "reason": "robot adapter not ready"}
        if abs(lateral) > 1e-4:
            return {"accepted": False, "reason": "selected differential robot does not support lateral motion", "unsupported_axis": "lateral"}
        action = self.controller.forward(np.array([linear, angular], dtype=np.float32))
        self.robot.apply_wheel_actions(action)
        return {"accepted": True, "adapter": self.adapter_name, "command": {"linear": linear, "lateral": 0.0, "angular": angular}}

    def stop(self) -> None:
        if self.ready:
            self.apply_motion(0.0, 0.0, 0.0)


class HolonomicDriveAdapter(WheeledAdapterBase):
    adapter_name = "holonomic-drive"

    def __init__(self, config: dict, scene: dict):
        super().__init__(config, scene)
        self._initialize()

    def _initialize(self) -> None:
        prim_path = str(self.config["prim_path"])
        wheel_names = list(self.config["wheel_dof_names"])
        spawn = np.asarray(robot_spawn(self.scene, self.config), dtype=np.float32)
        usd_path = asset_url(self.config["asset_path"])
        com_path = f"{prim_path.rstrip('/')}/{str(self.config['com_prim_subpath']).lstrip('/')}"

        try:
            enable_extension("isaacsim.robot.experimental.wheeled_robots")
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.robot.experimental.wheeled_robots.controllers import HolonomicController
            from isaacsim.robot.experimental.wheeled_robots.robots import HolonomicRobotUsdSetup, WheeledRobot

            self.robot = WheeledRobot(paths=prim_path, wheel_dof_names=wheel_names, usd_path=usd_path, positions=spawn.tolist(), orientations=[1.0, 0.0, 0.0, 0.0])
            setup = HolonomicRobotUsdSetup(robot_prim_path=prim_path, com_prim_path=com_path)
            params = setup.get_holonomic_controller_params()
            self.controller = HolonomicController(
                wheel_radius=params[0], wheel_positions=params[1], wheel_orientations=params[2],
                mecanum_angles=params[3], wheel_axis=params[4], up_axis=params[5]
            )
            SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cpu")
            try:
                scenes = SimulationManager.get_physics_scenes()
                if scenes:
                    scenes[0].set_enabled_gpu_dynamics(False)
            except Exception:
                pass
            self.api = "isaacsim.robot.experimental.wheeled_robots"
        except (ImportError, ModuleNotFoundError):
            enable_extension("isaacsim.robot.wheeled_robots")
            from isaacsim.robot.wheeled_robots.controllers import HolonomicController
            from isaacsim.robot.wheeled_robots.robots import WheeledRobot
            from isaacsim.robot.wheeled_robots.robots.holonomic_robot_usd_setup import HolonomicRobotUsdSetup

            self.robot = WheeledRobot(
                prim_path=prim_path,
                name=f"web_{self.config['id']}",
                wheel_dof_names=wheel_names,
                create_robot=True,
                usd_path=usd_path,
                position=spawn,
            )
            setup = HolonomicRobotUsdSetup(robot_prim_path=prim_path, com_prim_path=com_path)
            params = setup.get_holonomic_controller_params()
            self.controller = HolonomicController(
                name=f"web_holonomic_{self.config['id']}",
                wheel_radius=params[0], wheel_positions=params[1], wheel_orientations=params[2],
                mecanum_angles=params[3], wheel_axis=params[4], up_axis=params[5]
            )
            self.api = "isaacsim.robot.wheeled_robots"
        self._finish_init()

    def info(self) -> dict:
        return {
            **self._common_info(),
            "capabilities": {"forward": True, "lateral": True, "yaw": True},
        }

    def apply_motion(self, linear: float, lateral: float, angular: float) -> dict:
        if not self.ready:
            return {"accepted": False, "reason": "robot adapter not ready"}
        action = self.controller.forward(np.array([linear, lateral, angular], dtype=np.float32))
        self.robot.apply_wheel_actions(action)
        return {"accepted": True, "adapter": self.adapter_name, "command": {"linear": linear, "lateral": lateral, "angular": angular}}

    def stop(self) -> None:
        if self.ready:
            self.apply_motion(0.0, 0.0, 0.0)



class JointPositionAdapter(RobotAdapter):
    """Anything driven by per-joint targets rather than a wheel controller.

    The wheeled adapters expose motion(linear, lateral, angular), which has no
    meaning for an arm. Arms get set_joints({name: value}) instead, and report
    their joints so the browser can build a slider per axis.
    """

    adapter_name = "joint-position"

    def __init__(self, config: dict, scene: dict):
        self.config = dict(config)
        self.scene = dict(scene)
        self.robot = None
        self.api = "unknown"
        self.write_api = "unknown"
        self._write_fn = None
        self.root_fixed = False
        self.gains: dict = {}
        self.ready = False
        self.dof_names: list[str] = []
        self.limits: dict[str, list[float]] = {}
        self.home: dict[str, float] = {}
        self.targets: dict[str, float] = {}
        self._initialize()

    def _initialize(self) -> None:
        try:
            self._spawn_and_bind()
        except Exception:
            # Anything referenced onto the live stage must come back off it,
            # or a failed launch leaves a robot being simulated that no adapter
            # owns and nothing can drive.
            self._remove_prim()
            raise

    def _remove_prim(self) -> None:
        try:
            from isaacsim.core.utils.prims import delete_prim, is_prim_path_valid
            path = str(self.config["prim_path"])
            if is_prim_path_valid(path):
                delete_prim(path)
                for _ in range(2):
                    kit.update()
        except Exception as exc:
            print(f"[stage2] could not remove {self.config['prim_path']}: {exc}", flush=True)

    def _spawn_and_bind(self) -> None:
        prim_path = str(self.config["prim_path"])
        usd_path = asset_url(self.config["asset_path"])
        spawn = np.asarray(robot_spawn(self.scene, self.config), dtype=np.float32)

        from isaacsim.core.utils.stage import add_reference_to_stage
        add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)

        # Place it BEFORE anchoring. The articulation constructor below also
        # takes a position, but it runs after the anchor is authored -- and an
        # anchor computed at the origin while the body ends up metres away is a
        # constraint violation the solver cannot survive. This is only harmless
        # when the spawn happens to be the origin, which is exactly how it hid.
        self._place_at(prim_path, spawn)
        self.spawn = spawn
        self._apply_physics_tuning(prim_path)
        self.apply_drive_gains()
        if self.config.get("fix_root", True):
            self._fix_root_to_world(prim_path, spawn)

        # Try each candidate all the way through construction. Isaac has moved
        # these classes twice and the newer ones take paths=/positions= rather
        # than prim_path=/position=, so an import that succeeds proves nothing.
        candidates = (
            ("isaacsim.core.prims", "SingleArticulation",
             lambda cls: cls(prim_path=prim_path, name=f"web_{self.config['id']}", position=spawn)),
            ("isaacsim.core.experimental.prims", "Articulation",
             lambda cls: cls(paths=prim_path, positions=spawn.reshape(1, 3).tolist())),
            ("isaacsim.core.api.articulations", "Articulation",
             lambda cls: cls(prim_path=prim_path, name=f"web_{self.config['id']}", position=spawn)),
            ("omni.isaac.core.articulations", "Articulation",
             lambda cls: cls(prim_path=prim_path, name=f"web_{self.config['id']}", position=spawn)),
        )
        attempts = []
        self.robot = None
        for module, name, build in candidates:
            try:
                cls = getattr(__import__(module, fromlist=[name]), name)
            except (ImportError, ModuleNotFoundError, AttributeError) as exc:
                attempts.append(f"{module}.{name}: not available ({type(exc).__name__})")
                continue
            try:
                self.robot = build(cls)
                self.api = f"{module}.{name}"
                break
            except Exception as exc:
                attempts.append(f"{module}.{name}: {type(exc).__name__}: {exc}")
        if self.robot is None:
            raise RuntimeError("no usable articulation API in this Isaac Sim build:\n  " + "\n  ".join(attempts))
        print(f"[stage2] articulation api={self.api}", flush=True)

        try:
            from isaacsim.core.simulation_manager import SimulationManager
            policy_spec = self.config.get("policy") or {}
            physics_hz = float(policy_spec.get("physics_hz", 60.0))
            if not math.isfinite(physics_hz) or physics_hz <= 0.0:
                physics_hz = 60.0
            SimulationManager.setup_simulation(dt=1.0 / physics_hz, device="cpu")
            if policy_spec:
                print(f"[stage2] articulation simulation dt={1.0 / physics_hz:.6f}s "
                      f"({physics_hz:.0f} Hz)", flush=True)
        except Exception:
            pass

        timeline = omni.timeline.get_timeline_interface()
        if not timeline.is_playing():
            timeline.play()
        for _ in range(30):
            kit.update()
        try:
            self.robot.initialize()
        except Exception as exc:
            raise RuntimeError(f"articulation at {prim_path} would not initialize: {exc}") from exc
        for _ in range(10):
            kit.update()

        self._resolve_write()
        self.dof_names = list(getattr(self.robot, "dof_names", None) or [])
        if not self.dof_names:
            raise RuntimeError(
                f"{self.config['id']} has no drivable joints at {prim_path}; "
                "it may not be an articulation, or the wrong prim was referenced")
        self._read_limits()

        configured_home = dict(self.config.get("home_position") or {})
        current = self._current_positions()
        self.home = {}
        for name in self.dof_names:
            raw = configured_home.get(name)
            if raw is None:
                raw = current.get(name)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 0.0
            if not math.isfinite(value):
                value = 0.0
            # The catalog is user supplied; clamp it the same way set_joints does.
            low, high = self.limits.get(name, [-6.2832, 6.2832])
            self.home[name] = max(low, min(high, value))
        self.targets = dict(self.home)
        if configured_home:
            self._write(self.targets)

        if not self.is_stable():
            raise RuntimeError(
                "the articulation has non-finite transforms after initialisation - it "
                "exploded in physics. The usual cause is a free root link: a table-top "
                "arm must be anchored. Check the Isaac log for 'Illegal BroadPhaseUpdateData'.")
        self.ready = True
        unread = [n for n, v in current.items() if v is None]
        if unread:
            print(f"[stage2] {len(unread)} joint(s) read as NaN at spawn "
                  f"({', '.join(unread[:6])}); homing them to 0", flush=True)
        print(f"[stage2] robot ready id={self.config['id']} adapter={self.adapter_name} "
              f"api={self.api} write={self.write_api} dofs={len(self.dof_names)} "
              f"limits={len(self.limits)}", flush=True)

    def _read_limits(self) -> None:
        raw = None
        attempts = []
        for getter in ("get_dof_limits", "get_joint_limits"):
            try:
                raw = np.asarray(getattr(self.robot, getter)())
                break
            except Exception as exc:
                attempts.append(f"{getter}: {type(exc).__name__}")
        if raw is None:
            try:
                props = self.robot.dof_properties
                raw = np.stack([np.asarray(props["lower"]), np.asarray(props["upper"])], axis=-1)
            except Exception as exc:
                attempts.append(f"dof_properties: {type(exc).__name__}")
        if raw is None:
            print(f"[stage2] joint limits unavailable ({'; '.join(attempts)}); "
                  "teleop will be refused for this robot", flush=True)
            return
        if raw.ndim == 3:
            raw = raw[0]
        for index, name in enumerate(self.dof_names):
            # Per joint: a bad row must not cost every other joint its limits.
            try:
                low, high = float(raw[index][0]), float(raw[index][1])
            except (IndexError, TypeError, ValueError):
                continue
            if math.isfinite(low) and math.isfinite(high) and low < high:
                self.limits[name] = [low, high]
        missing = [n for n in self.dof_names if n not in self.limits]
        if missing:
            print(f"[stage2] no limits for {len(missing)} joint(s): {', '.join(missing[:6])}", flush=True)

    def _current_positions(self) -> dict:
        try:
            values = np.asarray(self.robot.get_joint_positions()).reshape(-1)
        except Exception:
            return {}
        out = {}
        for index, name in enumerate(self.dof_names):
            if index >= len(values):
                break
            value = float(values[index])
            # NaN escapes as bare `NaN` in JSON and the browser refuses it.
            out[name] = value if math.isfinite(value) else None
        return out

    def _place_at(self, prim_path: str, spawn) -> None:
        """Move the referenced prim to its spawn point on the stage."""
        try:
            from pxr import Gf, UsdGeom
            stage = omni.usd.get_context().get_stage()
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                return
            UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*[float(v) for v in spawn]))
            print(f"[stage2] placed {prim_path} at "
                  f"({float(spawn[0]):.3f}, {float(spawn[1]):.3f}, {float(spawn[2]):.3f})", flush=True)
        except Exception as exc:
            print(f"[stage2] could not place {prim_path}: {type(exc).__name__}: {exc}", flush=True)

    def _apply_physics_tuning(self, prim_path: str) -> None:
        """Bound the depenetration velocity, the way the reference config does.

        An arm that spawns interpenetrating the floor otherwise gets a huge
        corrective impulse on the first step and the solver never recovers.
        """
        try:
            from pxr import PhysxSchema, UsdPhysics
            stage = omni.usd.get_context().get_stage()
            root = stage.GetPrimAtPath(prim_path)
            if not root or not root.IsValid():
                return
            max_depen = float(self.config.get("max_depenetration_velocity", 5.0))
            touched = 0
            for prim in Usd.PrimRange(root):
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    api = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
                    api.CreateMaxDepenetrationVelocityAttr().Set(max_depen)
                    touched += 1
                if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                    art = PhysxSchema.PhysxArticulationAPI.Apply(prim)
                    art.CreateSolverPositionIterationCountAttr().Set(
                        int(self.config.get("solver_position_iterations", 32)))
                    art.CreateSolverVelocityIterationCountAttr().Set(
                        int(self.config.get("solver_velocity_iterations", 1)))
            print(f"[stage2] physics tuning applied to {touched} body/bodies "
                  f"under {prim_path} (max_depenetration={max_depen})", flush=True)
            friction = self.config.get("contact_friction")
            if friction is None:
                friction = (self.config.get("policy") or {}).get("contact_friction")
            if friction is not None:
                # Here, and not when a policy engages. Authoring under an
                # articulation makes PhysX re-parse it, and doing that after
                # the robot has been placed silently reverted its pose --
                # sometimes. The window was widened twice and never closed;
                # doing it before the articulation exists removes it.
                apply_contact_friction(prim_path, float(friction))
        except Exception as exc:
            print(f"[stage2] physics tuning skipped: {type(exc).__name__}: {exc}", flush=True)

    def _fix_root_to_world(self, prim_path: str, spawn) -> None:
        """Weld the articulation base to the world, at wherever it actually is.

        The anchor has to be the base link's real world transform, not the
        spawn point: the spawn is set on the parent prim and the base sits at
        its own offset below that. Anchoring to the spawn point instead means
        the joint tries to drag the body to a place it is not, and the solver
        blows up. That mistake is invisible when the spawn happens to be the
        origin and fatal everywhere else.
        """
        try:
            from pxr import Gf, Usd, UsdGeom, UsdPhysics
            stage = omni.usd.get_context().get_stage()
            base = None
            for prim in Usd.PrimRange(stage.GetPrimAtPath(prim_path)):
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    base = prim
                    break
            if base is None:
                print(f"[stage2] no rigid body under {prim_path}; root not fixed", flush=True)
                return

            world = UsdGeom.Xformable(base).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            translation = world.ExtractTranslation()
            rotation = world.ExtractRotationQuat()
            if not all(math.isfinite(float(v)) for v in translation):
                print(f"[stage2] base transform is not finite; root not fixed", flush=True)
                return

            joint_path = f"{prim_path}/WorldAnchor"
            joint = UsdPhysics.FixedJoint.Define(stage, joint_path)
            # body0 unset == the world frame.
            joint.CreateBody1Rel().SetTargets([base.GetPath()])
            joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*[float(v) for v in translation]))
            joint.CreateLocalRot0Attr().Set(Gf.Quatf(rotation))
            joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
            joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
            self.root_fixed = True
            drift = max(abs(float(translation[i]) - float(spawn[i])) for i in range(3))
            note = "" if drift < 0.5 else f"  WARNING: {drift:.2f}m from the spawn point"
            print(f"[stage2] root fixed: {joint_path} -> {base.GetPath()} "
                  f"at ({translation[0]:.3f}, {translation[1]:.3f}, {translation[2]:.3f}){note}", flush=True)
        except Exception as exc:
            print(f"[stage2] could not fix the root: {type(exc).__name__}: {exc}", flush=True)

    # Position targets alone make an arm oscillate: the solver is told where to
    # go but not how hard to pull or how much to resist. These are the drive
    # gains, and they are the difference between a steady arm and a shaking one.
    DEFAULT_GAINS = {"stiffness": 120.0, "damping": 25.0, "max_force": 60.0}

    def _joint_drive_prims(self):
        """Every drivable joint under this robot, with its drive type."""
        from pxr import UsdPhysics
        stage = omni.usd.get_context().get_stage()
        root = stage.GetPrimAtPath(str(self.config["prim_path"]))
        if not root or not root.IsValid():
            return []
        found = []
        for prim in Usd.PrimRange(root):
            type_name = str(prim.GetTypeName())
            if type_name == "PhysicsRevoluteJoint":
                found.append((prim, "angular"))
            elif type_name == "PhysicsPrismaticJoint":
                found.append((prim, "linear"))
        return found

    def apply_drive_gains(self, overrides: dict | None = None) -> dict:
        """Set stiffness / damping / max force on each joint drive."""
        from pxr import UsdPhysics
        per_joint = dict(self.config.get("joint_gains") or {})
        if overrides:
            for name, spec in overrides.items():
                merged = dict(per_joint.get(name) or {})
                merged.update(spec)
                per_joint[name] = merged
        base = dict(self.DEFAULT_GAINS)
        for key in base:
            if self.config.get(f"drive_{key}") is not None:
                base[key] = float(self.config[f"drive_{key}"])
        if overrides and "*" in overrides:
            base.update({k: float(v) for k, v in overrides["*"].items() if k in base})

        applied = {}
        for prim, drive_type in self._joint_drive_prims():
            name = prim.GetName()
            gains = {**base, **{k: float(v) for k, v in (per_joint.get(name) or {}).items() if k in base}}
            try:
                drive = UsdPhysics.DriveAPI.Apply(prim, drive_type)
                drive.CreateTypeAttr().Set("force")
                drive.CreateStiffnessAttr().Set(gains["stiffness"])
                drive.CreateDampingAttr().Set(gains["damping"])
                drive.CreateMaxForceAttr().Set(gains["max_force"])
                applied[name] = gains
            except Exception as exc:
                print(f"[stage2] drive gains failed on {name}: {type(exc).__name__}: {exc}", flush=True)
        self.gains = applied
        if applied:
            sample = next(iter(applied.values()))
            print(f"[stage2] drive gains applied to {len(applied)} joint(s) "
                  f"(default stiffness={sample['stiffness']} damping={sample['damping']} "
                  f"max_force={sample['max_force']})", flush=True)
        else:
            print("[stage2] no joint drives found; the arm will not hold position", flush=True)
        return applied

    def _resolve_write(self) -> None:
        """Pick the joint-target call now, not on the first slider drag."""
        errors = []
        try:
            from isaacsim.core.utils.types import ArticulationAction

            def apply(indices, values):
                self.robot.apply_action(ArticulationAction(
                    joint_positions=np.asarray(values, dtype=np.float32),
                    joint_indices=np.asarray(indices, dtype=np.int32),
                ))
            if hasattr(self.robot, "apply_action"):
                self._write_fn = apply
                self.write_api = "apply_action(ArticulationAction)"
                return
            errors.append("apply_action: not present on this articulation")
        except Exception as exc:
            errors.append(f"ArticulationAction: {type(exc).__name__}: {exc}")

        if hasattr(self.robot, "set_dof_position_targets"):
            def apply(indices, values):
                self.robot.set_dof_position_targets(
                    np.asarray([values], dtype=np.float32),
                    dof_indices=np.asarray(indices, dtype=np.int32),
                )
            self._write_fn = apply
            self.write_api = "set_dof_position_targets"
            return
        errors.append("set_dof_position_targets: not present")

        if hasattr(self.robot, "set_joint_position_targets"):
            def apply(indices, values):
                self.robot.set_joint_position_targets(
                    np.asarray(values, dtype=np.float32),
                    joint_indices=np.asarray(indices, dtype=np.int32),
                )
            self._write_fn = apply
            self.write_api = "set_joint_position_targets"
            return
        errors.append("set_joint_position_targets: not present")
        raise RuntimeError("no way to command joint targets on this articulation:\n  " + "\n  ".join(errors))

    def write_all(self, values) -> None:
        """Write every DOF in one call, for the policy loop.

        _write takes names because sliders and teleoperation speak in names.
        A policy speaks in indices and runs fifty times a second, so it gets a
        path that does not rebuild the mapping on every step.
        """
        self._write_fn(list(range(len(self.dof_names))), list(values))

    def _write(self, targets: dict) -> None:
        indices, values = [], []
        for name, value in targets.items():
            if name not in self.dof_names:
                continue
            indices.append(self.dof_names.index(name))
            values.append(float(value))
        if not indices:
            return
        self._write_fn(indices, values)

    def info(self) -> dict:
        # Set by duck_policy_driven() when the optional MicroDuck module is
        # present and has engaged this robot; always False in the no-duck build.
        driven = duck_policy_driven()
        return {
            "configured": True,
            "ready": self.ready,
            "id": self.config["id"],
            "name": self.config["name"],
            "adapter": self.adapter_name,
            "api": self.api,
            "write_api": self.write_api,
            "limits_known": bool(self.limits),
            "root_fixed": self.root_fixed,
            "policy_driven": driven,
            "gains": self.gains,
            "stable": self.is_stable() if self.robot is not None else False,
            "prim_path": self.config["prim_path"],
            "wheel_dof_names": [],
            "joint_names": self.dof_names,
            "joint_limits": self.limits,
            "joint_targets": self.targets,
            "home_position": self.home,
            # Expose the same motion envelope as wheeled adapters so the web
            # speed sliders do not fall back to their generic 0.5/0.4/1.5
            # defaults for a policy-driven biped. The bridge clamps again, but
            # the UI and the actual command must agree.
            "max_linear_speed": float(self.config.get("max_linear_speed", 0.5)),
            "max_lateral_speed": float(self.config.get("max_lateral_speed", 0.0)),
            "max_angular_speed": float(self.config.get("max_angular_speed", 1.5)),
            # A legged robot with a policy running takes W/A/S/D like any other
            # robot; without one it is a set of joints and nothing else. The
            # page builds its controls from this, so it has to say which.
            "capabilities": {
                "forward": driven, "lateral": driven, "yaw": driven, "joints": True,
            },
        }

    def apply_motion(self, linear: float, lateral: float, angular: float) -> dict:
        if linear == 0.0 and lateral == 0.0 and angular == 0.0:
            return {"accepted": True, "adapter": self.adapter_name, "note": "arm ignores base motion"}
        return {"accepted": False, "reason": "this robot is an arm; drive it with set_joints", "unsupported_axis": "base"}

    def set_joints(self, positions: dict, relative: bool = False) -> dict:
        if not self.ready:
            return {"accepted": False, "reason": "robot adapter not ready"}
        unknown = [name for name in positions if name not in self.dof_names]
        if unknown:
            raise ValueError(f"unknown joints: {', '.join(sorted(unknown))}")
        updated = {}
        for name, raw in positions.items():
            value = float(raw)
            if not np.isfinite(value):
                raise ValueError(f"joint {name} must be a finite number")
            if relative:
                value += self.targets.get(name, 0.0)
            low, high = self.limits.get(name, [-6.2832, 6.2832])
            value = max(low, min(high, value))
            self.targets[name] = value
            updated[name] = value
        self._write(updated)
        return {"accepted": True, "adapter": self.adapter_name, "targets": updated}

    def stop(self) -> None:
        # Holding position is the safe state for an arm; zeroing it would drop it.
        if self.ready:
            self._write(self.targets)

    def pose(self) -> dict | None:
        if self.robot is None:
            return None
        try:
            position, orientation = self.robot.get_world_pose()
            return _json_safe({
                "position": np.asarray(position).tolist(),
                "orientation_wxyz": np.asarray(orientation).tolist(),
                "joints": self._current_positions(),
                "stable": self.is_stable(),
            })
        except Exception:
            return _json_safe({"joints": self._current_positions(), "stable": self.is_stable()})

    def is_stable(self) -> bool:
        """False once physics has produced a non-finite transform.

        An exploded articulation still answers every query; it just has no
        valid position, so it renders nowhere and every command is pointless.
        Reporting `ready` in that state is the tool lying to the operator.
        """
        try:
            position, _ = self.robot.get_world_pose()
            return bool(np.all(np.isfinite(np.asarray(position, dtype=np.float64))))
        except Exception:
            return False

    def reset(self) -> dict:
        if not self.ready:
            return {"reset": False, "reason": "robot adapter not ready"}
        self.targets = dict(self.home)
        try:
            self.robot.set_joint_positions(np.asarray([self.home[n] for n in self.dof_names], dtype=np.float32))
        except Exception:
            pass
        self._write(self.targets)
        for _ in range(4):
            kit.update()
        return {"reset": True, "targets": self.targets}

