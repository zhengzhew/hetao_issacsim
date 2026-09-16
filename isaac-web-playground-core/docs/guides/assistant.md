# Telling it what to do in words

A chat panel at the top of the control column. You type what you want; a model
calls the playground's own operations to do it, and you watch each call happen.

## What it can do

Exactly what a person at the page can do, and nothing else:

| Tool | What it does |
|---|---|
| `get_session` | what scene and robot are loaded, and for an arm its joints, limits and targets |
| `list_catalog` | every scene and robot available, including uploads |
| `launch_session` | load a scene and robot together |
| `look` | **take a picture and look at it** |
| `drive` | drive a wheeled base for a set time, then stop |
| `set_joints` | move an arm |
| `home_robot` | back to the starting pose |
| `move_camera` | frame the robot, orbit, zoom, raise, reset |

Two of those need explaining.

**`look` is the only eye.** Without it the model is acting blind, and a model
that cannot check its own work will report a scene it never verified. The
system prompt tells it to look rather than assume, and the picture it got back
is rendered inline in the chat, so you can see what it saw.

**`drive` takes a duration** because the bridge stops the robot 0.4 s after the
last command — that is the motion watchdog, and it is deliberate. A single
command moves the robot a few centimetres. Making the model send its own
heartbeat would spend a network round trip every 100 ms, so the server holds
the command for the requested time and then stops.

## Wiring

This machine reaches Claude through NVIDIA's **OpenAI-compatible** gateway, not
the Anthropic API, so the wire format conversion lives in
`server/providers/gateway.js` — the only file that knows about that format.

    GATEWAY_BASE_URL=https://inference-api.nvidia.com/v1/chat/completions
    GATEWAY_API_KEY=<key>
    GATEWAY_MODEL=azure/anthropic/claude-sonnet-5

The model name must carry its full namespace — `azure/anthropic/claude-sonnet-5`,
not `claude-sonnet-5`. A bare name comes back as a 403 that reads like a bad
key ("this key can only access models=['default-models']"), which is misleading.
`GET /v1/models` on the same base URL lists what a key may actually use; that is
the answer, not guesswork.

`deploy/wsl/start-web.sh` picks these up from, in order: the environment,
`~/gateway.env` (mode 600, not in the repo), then
`~/.claude-code-router/config.json` if that machine happens to have one.

With no key the panel says so and the rest of the page works normally — the
assistant is additive, not load-bearing.

Check it with `GET /api/agent/status`.

## How a turn works

`POST /api/agent/message` returns `202` immediately; the work streams over
`GET /api/agent/events` (SSE). Everyone with the page open sees the same
conversation, because there is one simulation and therefore one conversation.

The loop runs at most 16 tool rounds. A tool that throws is handed back to the
model as an error result rather than ending the turn — reading a failure and
trying something else is usually better than dying.

History is trimmed to the last 40 messages, taking care not to leave a
`tool_result` whose `tool_use` has been dropped, which the API rejects.

## Endpoints

`GET /api/agent/events` · `GET /api/agent/status` ·
`POST /api/agent/message` · `POST /api/agent/reset`

## Not done

- **No approval gate.** The week-one console asked before anything dangerous;
  here every tool is bounded by the same limits the HTTP routes enforce, so
  there is nothing to gate — but that also means the assistant can switch
  scenes and move robots without asking.
- **No authentication**, same as the rest of the tool. Anyone who can reach the
  port can drive the robot by typing at it.
- **One conversation, shared.** Two people typing will interleave.
- **Verified against a stand-in gateway, not the real one.** The loop, tool
  execution, image round-trip, error recovery and the UI were all exercised end
  to end; the actual NVIDIA endpoint has not been called from this code.
