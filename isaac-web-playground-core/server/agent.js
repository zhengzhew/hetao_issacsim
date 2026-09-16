// The conversation loop: stream from the model, run whatever tools it asks
// for, feed the results back, repeat until it stops calling tools. Every step
// is pushed to the browser as it happens, so the operator watches the work
// rather than waiting for a verdict.
import { GatewayProvider } from './providers/gateway.js'
import { TOOL_DEFINITIONS, runAgentTool } from './agent-tools.js'

const SYSTEM_PROMPT = `You operate an NVIDIA Isaac Sim scene for someone who is watching the simulation in a browser beside this conversation.

Tools are the only way you can act, and \`look\` is the only way you can see. You have no other view of the scene.

How to work:
- Find out before you act. Call get_session before doing anything to "the robot" — whether it is a wheeled base or an arm changes which tools work at all.
- Check your work with \`look\` when a change should be visible. Do not report that something happened because a tool returned success; look at it.
- launch_session takes one to four minutes and throws away any teleoperation session. Only call it when the operator actually wants a different scene or robot.
- Independent calls in one turn run concurrently.

Do what was asked, at the scope intended. Make ordinary judgement calls yourself — a sensible distance, a reasonable joint angle — and say which you picked. Ask only when two readings of the request would produce materially different results.

Keep replies short. The operator is looking at the simulation; do not narrate what is now on their screen. One or two sentences: what you did, and any default you chose. Lead with the outcome.

When a tool fails, read the error and adapt. Say plainly what failed. Never claim the scene contains something unless a tool result says it does.`

const MAX_ITERATIONS = 16

export class Agent {
  constructor({ config, deps, emit }) {
    this.config = config
    this.deps = deps
    this.emit = emit
    this.messages = []
    this.busy = false
    this.provider = null
  }

  get configured() {
    return Boolean(this.config.gatewayBaseUrl && this.config.gatewayApiKey && this.config.gatewayModel)
  }

  get label() {
    return this.configured ? `${this.config.gatewayModel}` : 'not configured'
  }

  reset() {
    this.messages = []
  }

  async send(userText) {
    if (this.busy) throw new Error('the assistant is still working on the previous message')
    if (!this.configured) {
      throw new Error('no language model is configured; set GATEWAY_BASE_URL, GATEWAY_API_KEY and GATEWAY_MODEL')
    }
    // Built lazily so a missing key is a per-request error rather than a
    // startup crash that takes the whole playground down.
    if (!this.provider) this.provider = new GatewayProvider(this.config)

    this.busy = true
    this.messages.push({ role: 'user', content: String(userText) })
    this.emit({ type: 'user_message', text: String(userText) })
    try {
      await this.#loop()
    } catch (err) {
      this.emit({ type: 'error', message: err.message })
    } finally {
      this.busy = false
      this.emit({ type: 'turn_end' })
      this.#trim()
    }
  }

  async #loop() {
    for (let iteration = 0; iteration < MAX_ITERATIONS; iteration++) {
      const response = await this.provider.streamTurn({
        system: SYSTEM_PROMPT,
        messages: this.messages,
        tools: TOOL_DEFINITIONS,
        onEvent: this.emit,
      })

      if (response.stop_reason === 'refusal') {
        this.emit({ type: 'error', message: 'the model declined this request' })
        return
      }
      if (response.stop_reason === 'max_tokens') {
        this.emit({ type: 'error', message: 'the reply was cut off at the token limit' })
      }

      this.messages.push({ role: 'assistant', content: response.content })

      const calls = response.content.filter((block) => block.type === 'tool_use')
      if (!calls.length) return

      const results = await Promise.all(calls.map((call) => this.#execute(call)))
      this.messages.push({ role: 'user', content: results })
    }
    this.emit({ type: 'error', message: `stopped after ${MAX_ITERATIONS} tool rounds without finishing` })
  }

  async #execute(call) {
    this.emit({ type: 'tool_input', id: call.id, name: call.name, input: call.input })
    const started = Date.now()
    try {
      const { content, preview } = await runAgentTool(call.name, call.input, this.deps)
      this.emit({
        type: 'tool_end',
        id: call.id,
        name: call.name,
        ok: true,
        ms: Date.now() - started,
        summary: typeof content === 'string' ? content.slice(0, 300) : 'image returned',
        preview,
      })
      return { type: 'tool_result', tool_use_id: call.id, content }
    } catch (err) {
      this.emit({
        type: 'tool_end',
        id: call.id,
        name: call.name,
        ok: false,
        ms: Date.now() - started,
        summary: err.message.slice(0, 300),
      })
      // Handed back rather than thrown: the model should read the failure and
      // try something else, which is usually better than the turn dying.
      return { type: 'tool_result', tool_use_id: call.id, content: `Error: ${err.message}`, is_error: true }
    }
  }

  /** Keep the history bounded; images are large and old ones are rarely useful. */
  #trim() {
    const MAX_MESSAGES = 40
    if (this.messages.length <= MAX_MESSAGES) return
    const dropped = this.messages.length - MAX_MESSAGES
    // Drop from the front, but never leave a tool_result whose tool_use is gone.
    let cut = dropped
    while (cut < this.messages.length) {
      const msg = this.messages[cut]
      const isOrphanResult =
        msg.role === 'user' && Array.isArray(msg.content) && msg.content.some((b) => b.type === 'tool_result')
      if (!isOrphanResult) break
      cut += 1
    }
    this.messages = this.messages.slice(cut)
  }
}

export { SYSTEM_PROMPT, TOOL_DEFINITIONS }
