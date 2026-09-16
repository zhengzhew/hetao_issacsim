# --- locomotion policies -----------------------------------------------------
#
# Every other robot here moves because somebody holds a key down. A biped
# cannot: standing up is a learned behaviour, and the network that produces it
# was trained at a fixed rate. Feed it at the render rate and it falls over,
# with nothing in the log to say why.
#
# So this owns a clock. It advances physics at the rate the policy expects,
# runs inference every fourth step, and paces itself against the wall clock so
# the robot moves at the speed it would in the world.

POLICY = {
    "runner": None,
    "engaged": False,
    "command": [0.0, 0.0, 0.0],       # vx, vy, yaw rate
    # One clock, never rewound. PhysX is handed this as its current time, and
    # handing it a time that goes backwards is not something it is required to
    # survive. sim_anchor -- not sim_time -- is what an engage resets.
    "sim_time": 0.0,
    "wall_anchor": 0.0,
    "sim_anchor": 0.0,
    # "owned"  -- the timeline is paused and this loop is the only thing
    #             stepping physics, which is what the policy's fixed rate needs.
    # "shared" -- the probe below said that does not work on this build, so the
    #             timeline is left playing and kit.update() steps physics too.
    #             Then sim_time undercounts and "realtime" cannot be trusted.
    "clock": None,
    "timeline_at_engage": None,
    "timeline_advance": 0.0,
    "steps": 0,
    "inferences": 0,
    "realtime": 0.0,
    "dropped": 0.0,
    "engaged_at": 0.0,
    "start_xy": None,
    "library": {},
    "walk_file": None,
    "stand_file": None,
    "idle_since": 0.0,
    "episode_until": 0.0,
    "episode_return_to": None,
    "gains_now": None,
    "last_error": None,
}

# Beyond this the loop stops trying to catch up. A machine that falls behind
# and then sprints to make up the difference produces a robot that teleports,
# which is worse than one that runs slow and says so.
MAX_CATCHUP_STEPS = 40


class PolicyRunner:
    """One ONNX locomotion policy, driving one articulation.

    The observation layout is upstream's and is not negotiable: joint positions
    arrive relative to the home pose and actions are deltas from it. Both of
    those fail silently -- treat either as absolute and the robot simply never
    stands, with a clean log and 61 plausible numbers going into the network.
    """

    def __init__(self, adapter, spec: dict):
        self.adapter = adapter
        self.joints = [str(j) for j in spec["joints"]]
        self.home = np.asarray(spec["home"], dtype=np.float32)
        if len(self.joints) != len(self.home):
            raise ValueError("policy joints and home pose differ in length")
        policy_name = Path(str(spec["file"])).name
        per_file_scale = dict(spec.get("action_scale_by_file") or {})
        fallback_scale = float(spec.get("action_scale", 1.0))
        self.action_scale = float(
            per_file_scale.get(policy_name, action_scale_for_policy(policy_name, fallback_scale))
        )
        self.friction = float(spec.get("contact_friction", 1.0))
        # Where the root body belongs when standing, in world metres. Distinct
        # from the catalogue's spawn_z, which places the prim.
        self.stand_height = float(spec.get("stand_height", 0.125))
        # The raw Isaac-Sim DriveAPI path is retained for compatibility with
        # the existing deployment, but switching gains is isolated as an
        # explicit policy option because it is not part of the public runtime
        # contract and can create a transition transient.
        library = spec.get("gains_by_file") or {}
        self.gains = dict(library.get(policy_name) or {})
        self.switch_drive_gains = bool(spec.get("switch_drive_gains", True))
        self.physics_dt = 1.0 / float(spec.get("physics_hz", 200.0))
        self.decimation = int(spec.get("decimation", 4))
        self.control_dt = self.physics_dt * self.decimation
        self.obs_size = int(spec.get("obs_size", 61))
        self.command_size = int(spec.get("command_size", 13))
        limits = tuple(float(v) for v in (spec.get("command_limits") or VELOCITY_COMMAND_LIMITS))
        if len(limits) != 3:
            raise ValueError("policy command_limits must contain [vx, vy, yaw_rate]")
        self.command_limits = limits
        self.switch_threshold = float(spec.get("switch_threshold", 0.05))
        target_filter = dict(spec.get("target_filter") or {})
        self.head_lowpass = float(target_filter.get("head_alpha", 0.5))
        self.legs_lowpass = float(target_filter.get("legs_alpha", 0.7))

        path = Path(str(spec["file"]))
        if not path.is_absolute():
            path = resolve_upload(str(spec["file"]))
        if not path.is_file():
            raise FileNotFoundError(f"policy not found: {path}")

        import onnxruntime as ort
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        net_in = self.session.get_inputs()[0]
        net_out = self.session.get_outputs()[0]
        if int(net_in.shape[-1]) != self.obs_size or int(net_out.shape[-1]) != len(self.joints):
            raise ValueError(
                f"policy is {net_in.shape}->{net_out.shape}, expected "
                f"[1,{self.obs_size}]->[1,{len(self.joints)}]")
        self.input_name = net_in.name
        self.output_name = net_out.name
        self.session.run([self.output_name],
                         {self.input_name: np.zeros((1, self.obs_size), dtype=np.float32)})

        dof_names = list(adapter.dof_names)
        missing = [j for j in self.joints if j not in dof_names]
        if missing:
            raise ValueError(f"articulation is missing policy joints: {missing}")
        # Isaac does not report the DOFs in the policy's order -- on MicroDuck
        # it interleaves the legs with the neck. Skipping this map scrambles
        # every joint and looks like a policy that does not work.
        self.index_map = np.asarray([dof_names.index(j) for j in self.joints], dtype=np.int64)
        self.dof_count = len(dof_names)
        self.last_action = np.zeros(len(self.joints), dtype=np.float32)
        self.previous_target = self.home.copy()
        # Lightweight control diagnostics. These distinguish a noisy policy
        # target from a smooth target that PhysX/DriveAPI executes noisily.
        self.raw_target_delta_max = 0.0
        self.filtered_target_delta_max = 0.0
        self.filtered_target_delta_rms = 0.0
        self.name = path.name
        print(f"[stage2] policy {self.name}: {self.obs_size}->{len(self.joints)}, "
              f"{1.0 / self.control_dt:.0f} Hz control over {1.0 / self.physics_dt:.0f} Hz physics",
              flush=True)

    def stand_up(self) -> None:
        """Put the robot back on its feet before handing it to the policy.

        alpha_stand keeps a standing robot standing; it is not a get-up policy.
        Handed a robot lying face down it will fail, and nothing about that
        failure looks like the config being right.
        """
        robot = self.adapter.robot
        spawn = np.asarray(getattr(self.adapter, "spawn", [0.0, 0.0, 0.0]), dtype=np.float32)
        # spawn_z positions the prim's transform; set_world_pose moves the
        # articulation's ROOT BODY, and on this asset the trunk sits 12 cm
        # above the prim's origin. Passing one where the other belongs buries
        # the trunk at ankle height with the legs through the floor -- and the
        # robot then staggers and falls in a way that looks like a bad policy.
        position = np.array([spawn[0], spawn[1], self.stand_height], dtype=np.float32)
        upright = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        # Instrumented because two guesses about why this fails were both
        # wrong. Reading the quaternion before, immediately after, and again
        # once the frames have run separates "the write did not take" from
        # "the write took and something moved it".
        before = np.asarray(robot.get_world_pose()[1], dtype=np.float32)
        robot.set_world_pose(position=position, orientation=upright)
        written = np.asarray(robot.get_world_pose()[1], dtype=np.float32)
        print(f"[stage2] stand_up quaternion: before={before.round(3).tolist()} "
              f"after_write={written.round(3).tolist()}", flush=True)
        try:
            robot.set_linear_velocity(np.zeros(3, dtype=np.float32))
            robot.set_angular_velocity(np.zeros(3, dtype=np.float32))
        except Exception:
            pass
        full = np.zeros(self.dof_count, dtype=np.float32)
        full[self.index_map] = self.home
        try:
            robot.set_joint_positions(full)
            robot.set_joint_velocities(np.zeros(self.dof_count, dtype=np.float32))
        except Exception:
            pass
        self.adapter.write_all(full)
        for _ in range(3):
            kit.update()
        placed, settled_quat = robot.get_world_pose()
        settled_quat = np.asarray(settled_quat, dtype=np.float32)
        print(f"[stage2] stand_up quaternion: after_frames={settled_quat.round(3).tolist()} "
              f"height={float(placed[2]) * 100:.1f} cm", flush=True)
        if abs(float(placed[2]) - self.stand_height) > 0.05:
            raise RuntimeError(
                f"asked for the trunk at {self.stand_height:.3f} m but it reads back at "
                f"{float(placed[2]):.3f} m; the pose did not take, which usually means "
                "a stage edit triggered a physics resync after it was written")

    def settle(self, seconds: float = 0.3) -> None:
        """Hold the home pose while the contacts settle.

        The robot was just teleported into place. Handing the policy a first
        observation full of that impact makes a working policy look broken.
        """
        from omni.physx import get_physx_interface
        physx = get_physx_interface()
        full = np.zeros(self.dof_count, dtype=np.float32)
        full[self.index_map] = self.home
        for _ in range(int(seconds / self.physics_dt)):
            self.adapter.write_all(full)
            # The shared clock, not a local one starting at zero: settling is
            # physics like any other, and PhysX sees a single monotonic time.
            physx.update_simulation(self.physics_dt, POLICY["sim_time"])
            POLICY["sim_time"] += self.physics_dt
        _, orientation = self.adapter.robot.get_world_pose()
        position, _ = self.adapter.robot.get_world_pose()
        print(f"[stage2] policy settled at height {float(position[2]) * 100:.1f} cm", flush=True)

    def check_frame_convention(self) -> None:
        """Ask a question whose answer is already known, before trusting the rest.

        A robot standing upright must see gravity pointing straight down in its
        own frame. isaacsim.core reports orientation as (w, x, y, z) and Isaac
        Lab uses (x, y, z, w); take the wrong one and every rotated term in the
        observation is wrong while still looking entirely reasonable.

        This runs immediately after stand_up, so a failure means the convention
        really is wrong -- run before that, on a robot that has been lying on
        the floor since it loaded, it would fire every time and blame the wrong
        thing.
        """
        _, orientation = self.adapter.robot.get_world_pose()
        gravity = quat_rotate_inverse(np.asarray(orientation, dtype=np.float32),
                                      np.array([0.0, 0.0, -1.0], dtype=np.float32))
        if abs(float(gravity[2]) + 1.0) > 0.25:
            raise RuntimeError(
                f"after being stood upright the robot still sees gravity as "
                f"{gravity.round(3).tolist()} in its own frame rather than (0, 0, -1). "
                "Either the quaternion convention is wrong, or the robot did not "
                "actually come upright -- check the spawn height and whether the "
                "asset's rest orientation is the identity.")
        print(f"[stage2] policy frame check passed: gravity {gravity.round(3).tolist()}", flush=True)

    def observe(self, command) -> "object":
        robot = self.adapter.robot
        _, orientation = robot.get_world_pose()
        orientation = np.asarray(orientation, dtype=np.float32)
        ang_vel = quat_rotate_inverse(orientation, np.asarray(robot.get_angular_velocity(), dtype=np.float32))
        gravity = quat_rotate_inverse(orientation, np.array([0.0, 0.0, -1.0], dtype=np.float32))
        positions = np.asarray(robot.get_joint_positions(), dtype=np.float32)[self.index_map]
        velocities = np.asarray(robot.get_joint_velocities(), dtype=np.float32)[self.index_map]
        block = np.zeros(self.command_size, dtype=np.float32)
        block[0:3] = command
        return np.concatenate((
            ang_vel, gravity,
            positions - self.home,      # relative to home, never absolute
            velocities,
            self.last_action,
            block,
        )).astype(np.float32).reshape(1, self.obs_size)

    def clamp_command(self, command) -> list[float]:
        return list(clamp_velocity_command(command, self.command_limits))

    def control_step(self, command) -> None:
        """Run one inference and update a persistent, smoothed joint target."""
        safe_command = self.clamp_command(command)
        observation = self.observe(safe_command)
        if not np.isfinite(observation).all():
            raise RuntimeError("observation went non-finite")
        action = self.session.run([self.output_name],
                                  {self.input_name: observation})[0].reshape(len(self.joints))
        if not np.isfinite(action).all():
            raise RuntimeError("policy returned non-finite actions")
        self.last_action = action.astype(np.float32)
        raw_targets = self.home + self.action_scale * self.last_action
        previous_target = self.previous_target.copy()
        targets = np.asarray(
            smooth_position_targets(
                raw_targets,
                previous_target,
                head_alpha=self.head_lowpass,
                legs_alpha=self.legs_lowpass,
            ),
            dtype=np.float32,
        )
        raw_delta = raw_targets - previous_target
        filtered_delta = targets - previous_target
        self.raw_target_delta_max = float(np.max(np.abs(raw_delta)))
        self.filtered_target_delta_max = float(np.max(np.abs(filtered_delta)))
        self.filtered_target_delta_rms = float(np.sqrt(np.mean(filtered_delta * filtered_delta)))
        self.previous_target = targets.copy()
        full = np.zeros(self.dof_count, dtype=np.float32)
        full[self.index_map] = targets
        self.adapter.write_all(full)

    def adopt_state(self, previous) -> None:
        """Carry control history across a hot policy switch when layouts match."""
        if previous is None or list(previous.joints) != list(self.joints):
            self.reset()
            return
        self.last_action = np.asarray(previous.last_action, dtype=np.float32).copy()
        self.previous_target = np.asarray(previous.previous_target, dtype=np.float32).copy()
        self.raw_target_delta_max = float(getattr(previous, "raw_target_delta_max", 0.0))
        self.filtered_target_delta_max = float(getattr(previous, "filtered_target_delta_max", 0.0))
        self.filtered_target_delta_rms = float(getattr(previous, "filtered_target_delta_rms", 0.0))

    def reset(self) -> None:
        self.last_action = np.zeros(len(self.joints), dtype=np.float32)
        self.previous_target = self.home.copy()
        self.raw_target_delta_max = 0.0
        self.filtered_target_delta_max = 0.0
        self.filtered_target_delta_rms = 0.0


def quat_rotate_inverse(quat_wxyz, vector):
    """Rotate a world vector into the body frame. (w, x, y, z)."""
    w = quat_wxyz[0]
    q = quat_wxyz[1:]
    return (vector * (2.0 * w * w - 1.0)
            - np.cross(q, vector) * (2.0 * w)
            + q * (2.0 * float(np.dot(q, vector))))


def apply_contact_friction(prim_path: str, friction: float) -> int:
    """Give the robot's own colliders friction, rather than trusting the floor.

    A scene's ground is authored for whatever that scene was built for; the
    warehouse was not built with an 800 g biped in mind. PhysX combines the
    two materials, so raising the robot's side works whatever it is standing
    on, and modifies no scene.

    The binding goes on the root. Walking the descendants and binding each
    collider individually found nothing at all on this asset -- its geometry is
    instanced, and Usd.PrimRange does not enter instance prototypes by default.
    Material bindings inherit down the namespace, so one binding at the top
    reaches everything including the instanced parts.
    """
    try:
        from pxr import UsdPhysics, UsdShade
        stage = omni.usd.get_context().get_stage()
        root = stage.GetPrimAtPath(prim_path)
        if not root or not root.IsValid():
            print(f"[stage2] contact friction: no prim at {prim_path}", flush=True)
            return 0
        # Deliberately outside the robot's subtree. Authoring a prim under an
        # articulation makes PhysX re-parse it, and that resync landed after
        # stand_up had already placed the robot -- so the pose was silently
        # reverted to the asset's rest orientation and the frame check then
        # reported a robot lying on its face.
        material_path = "/World/PolicyContactMaterial"
        material = UsdShade.Material.Define(stage, material_path)
        api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        api.CreateStaticFrictionAttr().Set(float(friction))
        api.CreateDynamicFrictionAttr().Set(float(friction))
        api.CreateRestitutionAttr().Set(0.0)
        UsdShade.MaterialBindingAPI.Apply(root).Bind(
            material, UsdShade.Tokens.weakerThanDescendants, "physics")

        # Count what is actually down there, traversing into instances, so the
        # log says whether this reached anything rather than reporting success
        # for having authored one binding.
        colliders = sum(
            1 for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies())
            if prim.HasAPI(UsdPhysics.CollisionAPI))
        print(f"[stage2] contact friction {friction} bound at {prim_path} "
              f"({colliders} collider(s) beneath it)", flush=True)
        return colliders
    except Exception as exc:
        print(f"[stage2] could not set contact friction: {type(exc).__name__}: {exc}", flush=True)
        return 0


def policy_status() -> dict:
    runner = POLICY["runner"]
    # Position is reported as an observation, not as a baked-in pass/fail
    # threshold. Absolute MicroDuck speeds must be re-measured after the clock
    # path changes; stale shared-clock values should not become acceptance
    # criteria in code.
    travelled = None
    speed = None
    here = None
    heading = None
    if POLICY["engaged"] and runner is not None:
        try:
            position, orientation = runner.adapter.robot.get_world_pose()
            here = (float(position[0]), float(position[1]))
            q = np.asarray(orientation, dtype=np.float32)
            # Yaw from (w, x, y, z). Reported so a turn command can be checked
            # against how far the robot actually came round, rather than by
            # watching it.
            heading = math.degrees(math.atan2(
                2.0 * (q[0] * q[3] + q[1] * q[2]),
                1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3])))
            if POLICY["start_xy"] is None:
                raise ValueError
            travelled = math.hypot(here[0] - POLICY["start_xy"][0],
                                   here[1] - POLICY["start_xy"][1])
            wall = max(time.monotonic() - POLICY["engaged_at"], 1e-9)
            speed = travelled / wall
        except Exception:
            pass
    joint_velocity_rms = None
    joint_velocity_max = None
    if POLICY["engaged"] and runner is not None:
        try:
            velocities = np.asarray(runner.adapter.robot.get_joint_velocities(), dtype=np.float32)
            velocities = velocities[runner.index_map]
            if velocities.size:
                joint_velocity_rms = float(np.sqrt(np.mean(velocities * velocities)))
                joint_velocity_max = float(np.max(np.abs(velocities)))
        except Exception:
            pass
    return {
        "available": runner is not None,
        "name": getattr(runner, "name", None),
        "engaged": bool(POLICY["engaged"]),
        "command": list(POLICY["command"]),
        "command_limits": list(runner.command_limits) if runner else None,
        "action_scale": runner.action_scale if runner else None,
        "target_filter": ({"head_alpha": runner.head_lowpass, "legs_alpha": runner.legs_lowpass}
                          if runner else None),
        "control_metrics": ({
            "raw_target_delta_max_rad": round(runner.raw_target_delta_max, 5),
            "filtered_target_delta_max_rad": round(runner.filtered_target_delta_max, 5),
            "filtered_target_delta_rms_rad": round(runner.filtered_target_delta_rms, 5),
            "joint_velocity_rms_rad_s": (None if joint_velocity_rms is None
                                           else round(joint_velocity_rms, 4)),
            "joint_velocity_max_rad_s": (None if joint_velocity_max is None
                                           else round(joint_velocity_max, 4)),
        } if runner else None),
        "control_hz": round(1.0 / runner.control_dt, 1) if runner else None,
        "physics_hz": round(1.0 / runner.physics_dt, 1) if runner else None,
        "steps": POLICY["steps"],
        "inferences": POLICY["inferences"],
        "realtime": round(POLICY["realtime"], 3),
        # "owned": realtime means what it says. "shared": the renderer is
        # stepping physics too, so the robot is running faster than realtime
        # claims by an amount timeline_advance_s measures.
        "clock": POLICY["clock"],
        "timeline_advance_s": round(POLICY["timeline_advance"], 3),
        "dropped_seconds": round(POLICY["dropped"], 2),
        "travelled_m": None if travelled is None else round(travelled, 3),
        "drift_mps": None if speed is None else round(speed, 4),
        "position": None if here is None else [round(here[0], 4), round(here[1], 4)],
        "heading_deg": None if heading is None else round(heading, 2),
        "following": bool(FOLLOW["on"]),
        "error": POLICY["last_error"],
    }


def attach_policy(adapter, robot_cfg: dict) -> None:
    """Build the runner for a robot whose config names a policy."""
    release_physics_clock()
    POLICY.update({"runner": None, "engaged": False, "command": [0.0, 0.0, 0.0],
                   "steps": 0, "inferences": 0, "realtime": 0.0, "dropped": 0.0,
                   "engaged_at": 0.0, "last_error": None, "clock": None,
                   "timeline_at_engage": None, "timeline_advance": 0.0,
                   "start_xy": None, "library": {}, "walk_file": None,
                   "stand_file": None, "idle_since": 0.0, "episode_until": 0.0,
                   "episode_return_to": None, "gains_now": None})
    spec = robot_cfg.get("policy")
    if not spec:
        return
    try:
        POLICY["runner"] = PolicyRunner(adapter, dict(spec))
        POLICY["library"] = {POLICY["runner"].name: POLICY["runner"]}
        POLICY["stand_file"] = spec.get("stand_file") or POLICY["runner"].name
        POLICY["walk_file"] = spec.get("walk_file")
        # Load the walking policy now rather than on the first key press:
        # building a runner reads an ONNX file off disk, and doing that inside
        # the control loop would stall it long enough to drop the robot.
        for name in (spec.get("gains_by_file") or {}):
            if name in POLICY["library"]:
                continue
            try:
                alt = dict(spec)
                alt["file"] = str(Path(str(spec["file"])).parent / name).replace("\\", "/")
                POLICY["library"][name] = PolicyRunner(adapter, alt)
            except Exception as exc:
                print(f"[stage2] policy {name} not preloaded: {type(exc).__name__}: {exc}", flush=True)
    except Exception as exc:
        POLICY["last_error"] = f"{type(exc).__name__}: {exc}"
        print(f"[stage2] policy unavailable: {POLICY['last_error']}", flush=True)
        return
    # A biped with its policy switched off is a robot lying face down on the
    # floor. That is not a useful thing to show anyone who opens the page, and
    # it is indistinguishable from the load having failed.
    if spec.get("autostart", True):
        try:
            engage_policy()
            if spec.get("ball", True):
                # Loading a scene rebuilds the stage, so a ball spawned by hand
                # disappears the moment the robot is reloaded. It belongs with
                # the robot, not with the session it happened to be added in.
                spawn_arena(float(spec.get("pitch_size", 2.5)))
                spawn_ball()
        except Exception as exc:
            POLICY["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"[stage2] policy autostart failed: {POLICY['last_error']}", flush=True)


FOLLOW = {"on": False, "next_at": 0.0, "last": None, "hz": 10.0}


def start_following(prim_path: str) -> None:
    """Keep the robot in frame while it walks.

    A camera fixed on the spawn point is fine for an arm bolted to the floor.
    A robot that walks leaves the frame within seconds and is then being
    steered blind, which is most of what makes it hard to drive.

    Following pans the camera by however far the robot moved, and touches
    nothing else -- so zoom, angle and height stay wherever the operator put
    them.
    """
    FOLLOW["on"] = True
    FOLLOW["next_at"] = 0.0
    FOLLOW["last"] = None
    print(f"[stage2] camera following {prim_path} at {FOLLOW['hz']:g} Hz", flush=True)


def update_following() -> None:
    """Pan with the robot, and change nothing else.

    Re-running frame_robot kept the robot centred but recomputed the distance
    from its bounding box every time, so zooming out lasted a quarter of a
    second before being overridden -- the view was locked to one distance with
    no way to say otherwise.

    Moving the camera by the same delta as the robot leaves distance, angle
    and height exactly as the operator set them. There is no stored offset to
    go stale either: each update starts from wherever the camera actually is.
    """
    if not FOLLOW["on"] or POLICY["runner"] is None:
        return
    now = time.monotonic()
    if now < FOLLOW["next_at"]:
        return
    FOLLOW["next_at"] = now + 1.0 / max(FOLLOW["hz"], 0.1)
    try:
        position, _ = POLICY["runner"].adapter.robot.get_world_pose()
        here = (float(position[0]), float(position[1]), float(position[2]))
        last = FOLLOW["last"]
        FOLLOW["last"] = here
        if last is None:
            return
        delta = [here[i] - last[i] for i in range(3)]
        if max(abs(v) for v in delta) < 0.005:
            return
        apply_camera([CAMERA["eye"][i] + delta[i] for i in range(3)],
                     [CAMERA["target"][i] + delta[i] for i in range(3)])
    except Exception as exc:
        FOLLOW["on"] = False
        print(f"[stage2] camera following stopped: {type(exc).__name__}: {exc}", flush=True)


def spawn_arena(side: float = 2.5, wall_height: float = 0.10,
                thickness: float = 0.04, path: str = "/World/Pitch") -> dict:
    """A low wall around the play area, so a kicked ball stays findable.

    Upstream's kick and rally tasks run on a bounded pitch. Without one the
    ball rolls out of the scene on the first good kick and the demonstration
    can only be watched once.

    Static colliders, no rigid bodies: the walls are scenery that the ball
    bounces off, and nothing here should be able to knock them over.
    """
    from pxr import Gf, UsdGeom, UsdPhysics
    stage = omni.usd.get_context().get_stage()
    if stage.GetPrimAtPath(path):
        stage.RemovePrim(path)
    root = UsdGeom.Xform.Define(stage, path)

    centre = [0.0, 0.0]
    if POLICY["runner"] is not None:
        try:
            position, _ = POLICY["runner"].adapter.robot.get_world_pose()
            centre = [float(position[0]), float(position[1])]
        except Exception:
            pass

    half = float(side) / 2.0
    walls = (
        ("north", (0.0, half), (side, thickness)),
        ("south", (0.0, -half), (side, thickness)),
        ("east", (half, 0.0), (thickness, side)),
        ("west", (-half, 0.0), (thickness, side)),
    )
    for name, (dx, dy), (sx, sy) in walls:
        cube = UsdGeom.Cube.Define(stage, f"{path}/{name}")
        cube.CreateSizeAttr(1.0)
        cube.CreateDisplayColorAttr([Gf.Vec3f(0.85, 0.85, 0.88)])
        xform = UsdGeom.Xformable(cube.GetPrim())
        xform.AddTranslateOp().Set(
            Gf.Vec3d(centre[0] + dx, centre[1] + dy, wall_height / 2.0))
        xform.AddScaleOp().Set(Gf.Vec3f(float(sx), float(sy), float(wall_height)))
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

    print(f"[stage2] pitch {side:g} m square at "
          f"({centre[0]:.2f}, {centre[1]:.2f}), walls {wall_height * 100:.0f} cm",
          flush=True)
    return {"path": path, "centre": centre, "side": side, "wall_height": wall_height}


def spawn_ball(radius: float = 0.035, mass: float = 0.015,
               ahead: float = 0.22, path: str = "/World/Ball") -> dict:
    """Put a ball in front of the robot.

    70 mm across and 15 g, which is the ball the upstream kick task was
    trained against -- a heavier one simply will not move, and the kick looks
    like it failed.
    """
    from pxr import Gf, UsdGeom, UsdPhysics
    stage = omni.usd.get_context().get_stage()
    if stage.GetPrimAtPath(path):
        stage.RemovePrim(path)
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.CreateRadiusAttr(float(radius))
    sphere.CreateDisplayColorAttr([Gf.Vec3f(0.95, 0.35, 0.1)])

    origin = [0.0, 0.0]
    yaw = 0.0
    if POLICY["runner"] is not None:
        try:
            position, orientation = POLICY["runner"].adapter.robot.get_world_pose()
            origin = [float(position[0]), float(position[1])]
            # In front of the robot, not along world +X. Placed on the axis the
            # robot happens to be facing, a ball ends up beside or behind it as
            # soon as it turns, and the kick misses for a reason that has
            # nothing to do with the kick.
            q = np.asarray(orientation, dtype=np.float32)
            yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                             1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
        except Exception:
            pass
    placed = Gf.Vec3d(origin[0] + float(ahead) * math.cos(yaw),
                      origin[1] + float(ahead) * math.sin(yaw),
                      float(radius))
    UsdGeom.Xformable(sphere.GetPrim()).AddTranslateOp().Set(placed)

    UsdPhysics.RigidBodyAPI.Apply(sphere.GetPrim())
    UsdPhysics.CollisionAPI.Apply(sphere.GetPrim())
    UsdPhysics.MassAPI.Apply(sphere.GetPrim()).CreateMassAttr().Set(float(mass))
    print(f"[stage2] ball at {tuple(round(v, 3) for v in placed)}, "
          f"r={radius} m, {mass * 1000:.0f} g", flush=True)
    return {"path": path, "position": [placed[0], placed[1], placed[2]],
            "radius": radius, "mass": mass}


def ball_state(path: str = "/World/Ball") -> dict | None:
    from pxr import UsdGeom
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        return None
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    where = matrix.ExtractTranslation()
    return {"position": [round(float(where[i]), 4) for i in range(3)]}


def run_episode(name: str, seconds: float) -> dict:
    """Run a one-shot policy, then go back to whatever was running before.

    The kick policies are 0.5 s long and have no command input: they play out
    and stop. Leaving one loaded afterwards would keep the robot trying to
    kick nothing.
    """
    if not POLICY["engaged"]:
        raise ValueError("no policy is running")
    if name not in POLICY["library"]:
        raise ValueError(f"policy {name} is not loaded; add it to gains_by_file")
    POLICY["episode_return_to"] = POLICY["runner"].name
    use_policy(name)
    POLICY["episode_until"] = time.monotonic() + float(seconds)
    return policy_status()


def enforce_episode() -> None:
    """End a one-shot policy when its time is up."""
    if POLICY["episode_until"] <= 0.0 or time.monotonic() < POLICY["episode_until"]:
        return
    POLICY["episode_until"] = 0.0
    back = POLICY["episode_return_to"] or POLICY["stand_file"]
    POLICY["episode_return_to"] = None
    if back:
        use_policy(back)


def use_policy(name: str) -> bool:
    """Swap the active network without creating a one-frame control discontinuity."""
    runner = POLICY["library"].get(name)
    if runner is None or runner is POLICY["runner"]:
        return False
    started = time.monotonic()
    previous = POLICY["runner"]
    POLICY["runner"] = runner
    # The public playground keeps last_action and the filtered target alive
    # across policy changes. Zeroing them here injects an artificial step into
    # both the next observation and the next position target.
    runner.adopt_state(previous)
    if (runner.switch_drive_gains and runner.gains
            and runner.gains != POLICY.get("gains_now")):
        ROBOT.apply_drive_gains({"*": runner.gains})
        POLICY["gains_now"] = dict(runner.gains)
    print(f"[stage2] policy -> {runner.name} in {(time.monotonic() - started) * 1000:.1f} ms",
          flush=True)
    return True


def follow_command(command) -> None:
    """Stand when nothing is asked of it, walk when something is.

    alpha_stand does not respond to a velocity command -- standing still is
    the whole of what it was trained to do -- so leaving it loaded means the
    keys do nothing. alpha_stand also holds position far better than
    alpha_walking does, so keeping that one loaded means the robot creeps
    whenever it is left alone. Each policy does its own job.
    """
    if POLICY["episode_until"] > 0.0:
        return
    runner = POLICY["runner"]
    if runner is not None:
        command = runner.clamp_command(command)
        POLICY["command"] = list(command)
        moving = moving_command(command, runner.switch_threshold)
    else:
        moving = any(abs(float(v)) > 1e-3 for v in command)
    walk, stand = POLICY["walk_file"], POLICY["stand_file"]
    if moving and walk:
        POLICY["idle_since"] = 0.0
        use_policy(walk)
    elif not moving and stand:
        # A short delay before switching back, so tapping a key does not
        # thrash between two networks mid-stride.
        if POLICY["idle_since"] <= 0.0:
            POLICY["idle_since"] = time.monotonic()
        elif time.monotonic() - POLICY["idle_since"] > 0.25:
            use_policy(stand)


def engage_policy(command=None) -> dict:
    runner = POLICY["runner"]
    if runner is None:
        raise ValueError(POLICY["last_error"] or "this robot has no policy")
    if command is not None:
        POLICY["command"] = runner.clamp_command(command)
    else:
        POLICY["command"] = runner.clamp_command(POLICY["command"])
    runner.reset()
    if runner.switch_drive_gains and runner.gains:
        # Raw DriveAPI gain switching is a compatibility path, not part of the
        # MicroDuck policy contract. Keep it explicit so it can be disabled
        # when using one calibrated actuator setup for every policy.
        applied = ROBOT.apply_drive_gains({"*": runner.gains})
        POLICY["gains_now"] = dict(runner.gains)
        sample = next(iter(applied.values()), None) if isinstance(applied, dict) else None
        print(f"[stage2] policy gains for {runner.name}: asked {runner.gains}, "
              f"joints now {sample}", flush=True)
    # Order matters. The rate has to be authored before anything is stepped,
    # and the clock has to be taken before stand_up and settle -- those step
    # physics too, and doing them on the shared clock is the state this is
    # meant to leave behind.
    set_physics_rate(1.0 / runner.physics_dt)
    POLICY["clock"] = take_physics_clock(runner)
    runner.stand_up()
    runner.check_frame_convention()
    runner.settle()
    POLICY["engaged"] = True
    POLICY["wall_anchor"] = time.monotonic()
    POLICY["engaged_at"] = POLICY["wall_anchor"]
    # sim_time carries on from wherever it was; the anchor is what moves, so
    # the pacing below measures this engagement while the clock stays monotonic.
    POLICY["sim_anchor"] = POLICY["sim_time"]
    try:
        POLICY["timeline_at_engage"] = float(_timeline().get_current_time())
    except Exception:
        POLICY["timeline_at_engage"] = None
    POLICY["timeline_advance"] = 0.0
    POLICY["steps"] = 0
    POLICY["inferences"] = 0
    POLICY["dropped"] = 0.0
    try:
        position, _ = runner.adapter.robot.get_world_pose()
        POLICY["start_xy"] = (float(position[0]), float(position[1]))
    except Exception:
        POLICY["start_xy"] = None
    POLICY["last_error"] = None
    if CURRENT_ROBOT:
        start_following(str(CURRENT_ROBOT["prim_path"]))
    print(f"[stage2] policy engaged: {runner.name} command={POLICY['command']} "
          f"clock={POLICY['clock']}", flush=True)
    return policy_status()


def disengage_policy() -> dict:
    if POLICY["engaged"]:
        print("[stage2] policy disengaged", flush=True)
    POLICY["engaged"] = False
    release_physics_clock()
    return policy_status()


def _timeline():
    import omni.timeline
    return omni.timeline.get_timeline_interface()


# How far the robot must fall in FALL_STEPS of manual stepping for the probe
# below to count as proof. 12 steps at 200 Hz is 60 ms, and free fall over 60 ms
# is 1.8 cm; anything under 5 mm is contact noise, not physics running.
FALL_STEPS = 12
FALL_LIFT = 0.05
FALL_MIN = 0.005


def take_physics_clock(runner) -> str:
    """Make this loop the only thing that steps physics -- and check that it is.

    The policy wants 200 Hz. The main loop renders at about 12. Those are only
    separable if advance_policy() owns the stepping, and with the timeline
    playing it does not: kit.update() steps physics too, on a clock of its own
    that nothing here accounts for. Two clocks driving one scene means sim time
    runs faster than this module believes, and "realtime" -- computed from the
    steps this module took -- reports a number that cannot be wrong because it
    is not measuring the thing that is.

    So pause the timeline. That is the intent; whether it works on this build is
    a question about Isaac's internals, and guessing at those has been wrong
    here before. Ask the robot instead: lift it, step physics by hand, see
    whether it falls. That single measurement covers both halves of what the
    policy needs -- physics advanced, and the readback observe() uses saw it.

    If it fails, put the timeline back and carry on exactly as before. The
    policy still runs; it runs on a shared clock, and the log and the status
    both say so rather than leaving it to be inferred from a robot that walks
    at the wrong speed.
    """
    timeline = _timeline()
    if POLICY["sim_time"] <= 0.0:
        # First engage: start from wherever the timeline already is. Handing
        # PhysX a jump back to zero is the bug this function exists to avoid.
        try:
            POLICY["sim_time"] = float(timeline.get_current_time())
        except Exception:
            POLICY["sim_time"] = 0.0
    try:
        timeline.pause()
    except Exception as exc:
        print(f"[stage2] could not pause the timeline: {type(exc).__name__}: {exc}; "
              "physics stays on a shared clock", flush=True)
        return "shared"

    robot = runner.adapter.robot
    try:
        from omni.physx import get_physx_interface
        physx = get_physx_interface()
        spawn = np.asarray(getattr(runner.adapter, "spawn", [0.0, 0.0, 0.0]), dtype=np.float32)
        lifted = np.array([spawn[0], spawn[1], runner.stand_height + FALL_LIFT], dtype=np.float32)
        robot.set_world_pose(position=lifted, orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        robot.set_linear_velocity(np.zeros(3, dtype=np.float32))
        robot.set_angular_velocity(np.zeros(3, dtype=np.float32))
        # Home pose, not whatever it was left in. A crumpled robot can push
        # itself off the ground on its own collisions, and that would read as
        # "it did not fall" -- a false negative that costs the owned clock.
        full = np.zeros(runner.dof_count, dtype=np.float32)
        full[runner.index_map] = runner.home
        try:
            robot.set_joint_positions(full)
            robot.set_joint_velocities(np.zeros(runner.dof_count, dtype=np.float32))
        except Exception:
            pass
        runner.adapter.write_all(full)
        before = float(robot.get_world_pose()[0][2])
        for _ in range(FALL_STEPS):
            physx.update_simulation(runner.physics_dt, POLICY["sim_time"])
            POLICY["sim_time"] += runner.physics_dt
        fell = before - float(robot.get_world_pose()[0][2])
    except Exception as exc:
        print(f"[stage2] clock probe failed: {type(exc).__name__}: {exc}; "
              "leaving the timeline running", flush=True)
        try:
            timeline.play()
        except Exception:
            pass
        return "shared"

    if fell < FALL_MIN:
        print(f"[stage2] clock probe: robot fell {fell * 100:.2f} cm in "
              f"{FALL_STEPS} manual steps, expected at least {FALL_MIN * 100:.1f}; "
              "this build will not step physics with the timeline paused, so the "
              "policy runs on a clock it shares with the renderer and realtime "
              "is not a trustworthy number", flush=True)
        try:
            timeline.play()
        except Exception:
            pass
        return "shared"

    print(f"[stage2] policy owns the physics clock: timeline paused, robot fell "
          f"{fell * 100:.2f} cm in {FALL_STEPS} manual steps", flush=True)
    return "owned"


def release_physics_clock() -> None:
    """Hand the scene back to the renderer, so everything else still moves."""
    if POLICY.get("clock") != "owned":
        return
    try:
        _timeline().play()
        print("[stage2] physics clock released, timeline playing", flush=True)
    except Exception as exc:
        print(f"[stage2] could not restart the timeline: {type(exc).__name__}: {exc}", flush=True)
    POLICY["clock"] = None


def set_physics_rate(hz: float) -> None:
    """The policy assumes a physics rate; the stage carries whatever it was authored with."""
    try:
        from pxr import PhysxSchema, UsdPhysics
        stage = omni.usd.get_context().get_stage()
        scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
        prim = scenes[0] if scenes else UsdPhysics.Scene.Define(stage, "/PhysicsScene").GetPrim()
        PhysxSchema.PhysxSceneAPI.Apply(prim).CreateTimeStepsPerSecondAttr().Set(int(hz))
        print(f"[stage2] physics rate set to {hz:.0f} Hz on {prim.GetPath()}", flush=True)
    except Exception as exc:
        print(f"[stage2] could not set the physics rate: {type(exc).__name__}: {exc}", flush=True)


def advance_policy() -> None:
    """Advance physics and control at the policy's rate, paced to the wall clock.

    Called once per main-loop iteration, before kit.update(). With no policy
    engaged this does nothing at all and the loop behaves exactly as before.
    """
    runner = POLICY["runner"]
    if not POLICY["engaged"] or runner is None:
        return
    try:
        from omni.physx import get_physx_interface
        physx = get_physx_interface()
        elapsed = time.monotonic() - POLICY["wall_anchor"]
        behind = elapsed - (POLICY["sim_time"] - POLICY["sim_anchor"])
        steps = int(behind / runner.physics_dt)
        if steps <= 0:
            return
        if steps > MAX_CATCHUP_STEPS:
            # Give up on the missing time rather than sprint through it: a
            # robot that lurches to catch up is harder to diagnose than one
            # that runs slow. The abandoned time is counted, not hidden.
            skipped = steps - MAX_CATCHUP_STEPS
            POLICY["dropped"] += skipped * runner.physics_dt
            POLICY["wall_anchor"] += skipped * runner.physics_dt
            steps = MAX_CATCHUP_STEPS
        for index in range(steps):
            if POLICY["steps"] % runner.decimation == 0:
                runner.control_step(POLICY["command"])
                POLICY["inferences"] += 1
            physx.update_simulation(runner.physics_dt, POLICY["sim_time"])
            POLICY["sim_time"] += runner.physics_dt
            POLICY["steps"] += 1
        # Physics steps actually taken against wall time actually spent. The
        # earlier version divided by a moving anchor, so it reported 1.0 no
        # matter how much time was being dropped -- a metric that could not
        # fail is a metric that says nothing.
        wall = time.monotonic() - POLICY["engaged_at"]
        if wall > 0.5:
            POLICY["realtime"] = (POLICY["steps"] * runner.physics_dt) / wall
        # And how far the timeline moved meanwhile. On an owned clock this
        # stays at zero; anything else is physics being stepped by something
        # other than this loop, which is the failure "realtime" alone cannot
        # see. Reported rather than assumed, because the pause above is a
        # claim about Isaac's internals and this is the check on it.
        if POLICY["timeline_at_engage"] is not None:
            try:
                POLICY["timeline_advance"] = (
                    float(_timeline().get_current_time()) - POLICY["timeline_at_engage"])
            except Exception:
                pass
    except Exception as exc:
        POLICY["engaged"] = False
        POLICY["last_error"] = f"{type(exc).__name__}: {exc}"
        print(f"[stage2] policy stopped: {POLICY['last_error']}", flush=True)
        # A stopped policy that kept the timeline paused would freeze every
        # other robot on the stage along with it.
        release_physics_clock()

