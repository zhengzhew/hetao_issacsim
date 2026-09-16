# Trimming Isaac Sim to what this tool actually uses

## What was being paid for and not used

Isaac Sim was launched with the stock configuration, which meant:

- **The WebRTC livestream was enabled even in compatibility mode.** It holds an
  NVENC encoder session and a set of streaming threads regardless of whether
  anything is watching, and it cannot cross a NATing VPN — so on this
  deployment it had no consumer at all. It is also what produced the
  `NVST_R_BUSY` and `Cannot transition from current state` errors in the log.
- **The viewport rendered at 1280x720 while the capture reads 960x540.** The
  extra pixels were rendered and discarded.
- **The Kit editor UI was drawn.** It is only ever visible over WebRTC; the
  Replicator capture reads the viewport directly and never sees it.

## New defaults

    render      = capture size (960x540)
    hide_ui     = true
    livestream  = off

Nothing else changed. The full `isaacsim.exp.base` experience is still loaded —
switching to a lighter Kit experience file is the one trim that could plausibly
break a dependency, so it is not done here.

## Getting WebRTC back

    call python.bat C:\playground\bridge\isaac_playground.py ^
      --host 0.0.0.0 --port 8765 --public-ip <host-ip> ^
      --catalog-dir C:\playground\configs --upload-dir C:\playground\uploads ^
      --scene-id warehouse --robot-id carter-v1 ^
      --livestream

Set `ISAAC_STREAM_RENDERER=native` in `start-web.sh` at the same time. The two
must agree, or the page shows a Connect button that can never succeed.

`--livestream` restores the old behaviour: 1280x720, UI drawn, signalling on
49100 and media on 47998. Use it when the viewer is on the same network and you
want 60 fps. It will still not work through a VPN that NATs the client.

## Flags

| Flag | Default | Effect |
|---|---|---|
| `--livestream` / `--no-livestream` | off | WebRTC encoder and streaming threads |
| `--hide-ui` / `--show-ui` | hidden unless livestream is on | draws the Kit editor UI |
| `--render-width` / `--render-height` | capture size, or 1280x720 with livestream | viewport resolution |

`ISAAC_LIVESTREAM=1`, `ISAAC_RENDER_WIDTH`, `ISAAC_RENDER_HEIGHT` do the same
through the environment.

The active values are printed at startup and reported in `ping`, and the page
shows them under **Developer diagnostics → Renderer**, so a trimmed deployment
is visible without going to the machine.

## What the measurement actually said

Measured with `tools/measure_trim.py`, GPU utilisation as a percentage.
This box has two RTX PRO 5000s and a T400; the T400 stayed at 0 throughout and
is omitted.

| | GPU 0 | GPU 1 | total |
|---|---|---|---|
| **before any trimming**, idle | 32.9 | 26.2 | **59.1** |
| after idle throttling, idle | 10.8 | 0.9 | **11.7** |
| after idle throttling, 1 viewer | 33.2 | 23.0 | 56.2 |
| after idle throttling, 3 viewers | 33.1 | 24.3 | 57.4 |
| **single GPU**, idle | **0.0** | 14.3 | 14.3 |
| **single GPU**, 1 viewer | **0.0** | 75.6 | 75.6 |
| **single GPU**, 3 viewers | **0.0** | 75.7 | 75.7 |

Delivered frame rate, single GPU: **0 fps idle, 12.4 fps with a viewer** — the
configured 12, with nothing dropped despite GPU 1 sitting at 75 %.

**Idle was the whole problem, and none of the original trimming touched it.**
Isaac renders flat out whether or not anyone is watching: 59 points of GPU
burned to display nothing. Throttling the loop to 5 Hz when there is no viewer,
no teleop session and no recent command takes that to 11.7. This is the single
largest saving available and it was invisible until it was measured.

**Extra viewers really are free.** Three viewers cost the same as one, to
within a point, in both configurations. The shared capture loop does what it
claimed — this time on clean data. (The first measurement appeared to show the
same thing, but only because idle noise swamped everything; that reading was
worthless.)

**Stream resolution does cost GPU, contrary to what this document said an hour
earlier.** Quartering the pixel count saves ~12 points on GPU 1 with multi-GPU
on, but only ~3 points pinned to one GPU. The difference is the cross-GPU copy,
which scales with frame size — peer access is unavailable on this box, so those
copies go through main memory. The earlier claim that resolution was
"network-only" came from the noisy first measurement and was wrong.

**One GPU is the right setting here.** Pinned, Isaac uses GPU 1 alone and still
delivers the full frame rate; GPU 0 falls to 277 MB and 0 %, which matters
because this machine also holds unrelated training data. Total utilisation is
higher pinned (75 vs 56), so multi-GPU does genuinely distribute work — but
distributing it costs a copy tax and a whole second GPU, for frames that were
already arriving on time.

A caution that applies to all of the above: **single-digit differences here are
noise.** The first measurement produced two confident conclusions and one of
them was wrong. Use 20 s windows and be suspicious of anything small.

## Measure it, do not guess

`tools/gpu_probe.py` samples `nvidia-smi` and reports per-GPU utilisation and
memory. This box has more than one GPU, so "the GPU is busy" is not a useful
sentence — the tool splits them out.

    python3 gpu_probe.py --seconds 20 --label idle    --out idle.json
    python3 gpu_probe.py --seconds 20 --label viewing --out viewing.json
    python3 gpu_probe.py --compare idle.json viewing.json

Do this before and after the change. **No numbers have been measured yet** —
this machine has no GPU, so the savings above are reasoned from what the
settings control, not observed. The first real measurement should be:

1. idle, with the old settings (`--livestream --show-ui --render-width 1280 --render-height 720`)
2. idle, with the new defaults
3. one viewer connected, new defaults
4. three viewers connected, new defaults

Step 3 versus 4 also answers a separate open question: whether the shared
capture loop really does make extra viewers free on the GPU.

## One thing worth checking while you are there

The startup log shows this machine has at least two GPUs:

    Usdrt Hydra CUDA Peer Memory Copies from device[0] to device[1] is NOT possible

If training runs on the same box, confirm whether it and Isaac Sim are on the
same card. `gpu_probe.py` lists processes per GPU. If they collide, pin Isaac
with `CUDA_VISIBLE_DEVICES`.


## Correction, 2026-09-04: single GPU was not free

This document said single-GPU kept the frame rate while freeing GPU0. It does
not. Timing the three phases of the bridge's main loop shows:

| | `kit.update()` | whole loop |
|---|---|---|
| `--no-multi-gpu` | 70 ms | 9.8 Hz |
| `--multi-gpu` | 21.8 ms | 43.3 Hz |

Rendering is **3.2x slower on one GPU**. The earlier measurement missed it
because the capture rate is capped at 12 fps by default: single-GPU rendering
lands at about 12 Hz, which is exactly the cap, so the stream reported "full
rate" while two thirds of the rendering throughput had gone. A metric pinned
against its own ceiling cannot measure anything below that ceiling.

The trade-off is real and now stated honestly:

| | multi-GPU | single GPU |
|---|---|---|
| Stream | up to ~30 fps with a policy running | ~10 fps |
| GPU0 | ~2.8 GB, 33% | free |

Driving a legged robot at 10 fps is genuinely difficult -- that is what
prompted the measurement. If GPU0 is needed for training, the frame rate is
the price, and it should be paid knowingly rather than discovered.

### How the bottleneck was found

Timing each phase of the loop separately and printing a line every ten
seconds:

    [stage2] loop 43.3 Hz | requests+capture 1.3 ms, policy 0.0 ms, render 21.8 ms

Three earlier guesses at what was slow -- the physics stepping, the capture
resolution, the configured fps cap -- were all wrong, and each cost a restart
to disprove. The measurement took one commit and answered it immediately.
