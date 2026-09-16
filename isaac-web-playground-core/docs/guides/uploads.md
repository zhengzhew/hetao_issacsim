# Uploading your own scenes and robots

## Deploying this

Uploads land in a directory **both** processes can see. The web server normally
runs in WSL and the bridge on Windows, so the same directory has two spellings
and each side is configured separately:

    web server (WSL)      ISAAC_UPLOAD_DIR=/mnt/c/playground/uploads
    bridge     (Windows)  --upload-dir C:\playground\uploads

Get this wrong and uploads will appear to succeed while the simulator reports
`uploaded asset not found`.

## The flow

1. **Change scene / robot** → *Your own assets* → pick a `.usd` / `.usda` /
   `.usdc` / `.usdz` file → **Upload**.
2. The file is opened on its own USD stage (the live simulation is untouched)
   and the page reports prim count, up axis, articulation roots and every
   drivable joint it found.
3. Choose **As robot** or **As scene**, give it an id, and for a robot pick
   which joints to drive.
4. **Add to library** — it appears alongside the built-ins, tagged *yours*, and
   can be launched immediately.

Joint limits are reported with their unit. USD angular limits are **degrees**
while Isaac drives **radians**, so revolute joints carry both `limits` (degrees)
and `limits_rad`. A joint with no authored limits — any free-spinning wheel —
reports `limits: null, unlimited: true` rather than infinity.

Step 2 is the point of the whole feature. A USD file does not say which joints
are wheels and which are arm axes, and a wrong name surfaces much later as an
opaque `Invalid DOF name`, which is what happened with Nova Carter.

## Drive types

| Type | Needs | Control |
|---|---|---|
| `differential-drive` | exactly 2 wheel joints, wheel radius, wheel base | WASD |
| `holonomic-drive` | 3+ wheel joints, a centre-of-mass prim subpath | WASD + Q/E strafe |
| `joint-position` | any number of joints | one slider per joint |

### Arms need anchoring, and this is not optional

A table-top arm uploaded into a scene will **explode in physics** if its base is
free: it interpenetrates the floor, PhysX produces non-finite transforms, and
the whole simulator can die under the resulting contact load. Observed with
SO-101 in a warehouse scene — thousands of
`Dropping contacts ... exceeded limit of 32 friction patches` followed by the
Kit process exiting.

So `joint-position` robots get, by default:

- a **fixed joint to the world** on the base link (`fix_root`, default on),
- `max_depenetration_velocity` bounded to 5.0,
- **drive gains** on every joint (`drive_stiffness` 50, `drive_damping` 5,
  `drive_max_force` 30). Position targets alone make an arm oscillate: the
  solver is told where to go but not how hard to pull or how much to resist.

Gains can be retuned at runtime without restarting Isaac, which turns a two
minute loop into a one second one:

    curl -X POST http://host:8080/api/robot/gains \
      -H 'Content-Type: application/json' \
      -d '{"gains":{"*":{"damping":15}}}'

Shaking means more damping; sluggish means more stiffness; unable to hold its
own weight means more max_force. Per-joint overrides use the joint name in
place of `*`.

The adapter refuses to report `ready` if the articulation has non-finite
transforms after initialisation, so an exploded arm surfaces as a launch error
rather than a green light and an invisible robot.

`joint-position` is for arms. Base motion is meaningless there, so `motion()`
is refused and the WASD block hides itself; `set_joints` drives it instead.
Limits are read from the USD, and `stop()` holds position rather than zeroing
it — an arm told to go to zero would drop.

## Multi-file USD

Only self-contained files work today. A USD that references sibling textures or
sub-layers needs those files uploaded too, under the same relative names —
subdirectories in the upload name are allowed (`arm/base.usd`). `.usdz` is the
reliable option because it is self-contained by construction.

## Where things live

- files: `<upload dir>/<name>`
- user catalog: `<upload dir>/catalog.json`, merged over the built-in catalogs
  at startup and on every change. A user entry with the same id replaces a
  built-in, so a built-in can be corrected without editing `configs/`.

## Endpoints

`GET/POST /api/assets` · `DELETE /api/assets/<name>` ·
`POST /api/assets/inspect` · `POST /api/catalog/scenes` ·
`POST /api/catalog/robots` · `DELETE /api/catalog/{scenes,robots}/<id>` ·
`POST /api/robot/joints`

Uploads are capped by `ISAAC_UPLOAD_MAX_BYTES` (512 MB), streamed to disk, and
restricted to the four USD extensions. Names are rejected if they contain `..`
or resolve outside the upload directory, and a file still referenced by a
catalog entry cannot be deleted.

**Note:** this endpoint accepts files from anyone who can reach the port, and
there is still no authentication. That was an acceptable trade-off when the
catalog was fixed; it is a different trade-off now.
