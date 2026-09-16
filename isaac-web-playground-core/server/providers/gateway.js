// OpenAI-compatible chat/completions provider, for Claude served through a
// corporate gateway (e.g. NVIDIA's inference-api) rather than the Anthropic API.
//
// The rest of the app stays Anthropic-shaped — this file is the only place that
// knows about the other wire format. It converts in both directions:
//
//   messages / tools   Anthropic  →  OpenAI
//   streamed response  OpenAI     →  Anthropic content blocks
//
// Capability gap vs the Anthropic path, by construction: no adaptive thinking,
// no `effort`, no prompt-cache breakpoints, no server-side refusal fallbacks.
// Some gateways surface reasoning as `reasoning_content`; we map that to
// thinking deltas when present.

/** Anthropic tool defs → OpenAI function defs. */
function convertTools(tools) {
  return tools.map(({ name, description, input_schema }) => ({
    type: 'function',
    function: { name, description, parameters: input_schema },
  }))
}

/**
 * Anthropic messages → OpenAI messages.
 *
 * Two shapes need care:
 *  - tool results become `role: "tool"` messages keyed by tool_call_id;
 *  - an image inside a tool result cannot ride on a tool message, so it is
 *    re-attached as a following user message with image parts.
 */
function convertMessages(system, messages) {
  const out = [{ role: 'system', content: system }]

  for (const msg of messages) {
    if (msg.role === 'user') {
      if (typeof msg.content === 'string') { out.push({ role: 'user', content: msg.content }); continue }

      const trailingImages = []
      for (const block of msg.content) {
        if (block.type !== 'tool_result') continue
        let text = ''
        if (typeof block.content === 'string') {
          text = block.content
        } else {
          for (const part of block.content ?? []) {
            if (part.type === 'text') text += (text ? '\n' : '') + part.text
            else if (part.type === 'image') {
              trailingImages.push({
                type: 'image_url',
                image_url: { url: `data:${part.source.media_type};base64,${part.source.data}` },
              })
              text += (text ? '\n' : '') + '[image returned; see the attached image]'
            }
          }
        }
        out.push({ role: 'tool', tool_call_id: block.tool_use_id, content: text || '(empty)' })
      }
      if (trailingImages.length) {
        out.push({ role: 'user', content: [{ type: 'text', text: 'Here is the image from that tool call.' }, ...trailingImages] })
      }
      continue
    }

    // assistant: text becomes content, tool_use becomes tool_calls, thinking is
    // dropped (it is Anthropic-specific and the gateway model will reject it).
    const text = msg.content.filter((b) => b.type === 'text').map((b) => b.text).join('')
    const toolCalls = msg.content.filter((b) => b.type === 'tool_use').map((b) => ({
      id: b.id,
      type: 'function',
      function: { name: b.name, arguments: JSON.stringify(b.input ?? {}) },
    }))
    const entry = { role: 'assistant', content: text || null }
    if (toolCalls.length) entry.tool_calls = toolCalls
    out.push(entry)
  }
  return out
}

const STOP_REASON = { tool_calls: 'tool_use', stop: 'end_turn', length: 'max_tokens', content_filter: 'refusal' }

export class GatewayProvider {
  constructor(config) {
    this.config = config
    if (!config.gatewayBaseUrl) throw new Error('GATEWAY_BASE_URL is required for LLM_PROVIDER=gateway')
    if (!config.gatewayApiKey) throw new Error('GATEWAY_API_KEY is required for LLM_PROVIDER=gateway')
  }

  get label() { return `gateway · ${this.config.gatewayModel}` }

  async streamTurn({ system, messages, tools, onEvent }) {
    const res = await fetch(this.config.gatewayBaseUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.gatewayApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: this.config.gatewayModel,
        max_tokens: 16000,
        stream: true,
        messages: convertMessages(system, messages),
        tools: convertTools(tools),
        tool_choice: 'auto',
      }),
      signal: AbortSignal.timeout(600_000),
    })

    if (!res.ok) {
      const detail = (await res.text().catch(() => '')).slice(0, 400)
      throw new Error(`gateway ${res.status} ${res.statusText}${detail ? `: ${detail}` : ''}`)
    }

    return this.#consume(res, onEvent)
  }

  async #consume(res, onEvent) {
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let text = ''
    let started = false
    let thinkingStarted = false
    let finish = null
    const calls = new Map() // index → { id, name, args }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })

      let nl
      while ((nl = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, nl).trim()
        buf = buf.slice(nl + 1)
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (payload === '[DONE]') continue

        let chunk
        try { chunk = JSON.parse(payload) } catch { continue }
        if (chunk.error) throw new Error(`gateway: ${chunk.error.message || JSON.stringify(chunk.error)}`)

        const choice = chunk.choices?.[0]
        if (!choice) continue
        if (choice.finish_reason) finish = choice.finish_reason
        const delta = choice.delta || {}

        if (delta.reasoning_content) {
          if (!thinkingStarted) { thinkingStarted = true; onEvent({ type: 'thinking_start' }) }
          onEvent({ type: 'thinking_delta', text: delta.reasoning_content })
        }
        if (delta.content) {
          if (!started) { started = true; onEvent({ type: 'text_start' }) }
          text += delta.content
          onEvent({ type: 'text_delta', text: delta.content })
        }
        for (const tc of delta.tool_calls ?? []) {
          const idx = tc.index ?? 0
          if (!calls.has(idx)) {
            const entry = { id: tc.id || `call_${idx}`, name: tc.function?.name || '', args: '' }
            calls.set(idx, entry)
            if (entry.name) onEvent({ type: 'tool_start', id: entry.id, name: entry.name })
          }
          const entry = calls.get(idx)
          if (tc.id) entry.id = tc.id
          if (tc.function?.name && !entry.name) {
            entry.name = tc.function.name
            onEvent({ type: 'tool_start', id: entry.id, name: entry.name })
          }
          if (tc.function?.arguments) entry.args += tc.function.arguments
        }
      }
    }

    const content = []
    if (text) content.push({ type: 'text', text })
    for (const { id, name, args } of calls.values()) {
      let input = {}
      // A malformed argument string is the model's mistake, not ours — pass an
      // empty object through so the tool layer reports a usable error.
      try { input = args ? JSON.parse(args) : {} } catch { input = {} }
      content.push({ type: 'tool_use', id, name, input })
    }

    return {
      content,
      stop_reason: calls.size ? 'tool_use' : (STOP_REASON[finish] ?? 'end_turn'),
    }
  }
}

export { convertMessages, convertTools }
