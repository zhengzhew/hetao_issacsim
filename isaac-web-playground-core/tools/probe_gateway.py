#!/usr/bin/env python3
"""Find a working LLM route, by trying instead of guessing.

Run this on the machine that will host the playground. It sends one tiny
chat/completions request per candidate and reports the status, so a wrong
base URL or a stale key is a line of output rather than a redeploy.

    python3 probe_gateway.py --key sk-... --key sk-other

It prints a ready-to-use gateway.env for whichever combination answers.
Standard library only; nothing is written unless --write is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# Endpoints seen on NVIDIA machines. Order is most likely first.
DEFAULT_URLS = [
    "https://inference-api.nvidia.com/v1/chat/completions",
    "https://integrate.api.nvidia.com/v1/chat/completions",
    "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions",
]

DEFAULT_MODELS = ["azure/anthropic/claude-sonnet-5", "azure/anthropic/claude-opus-4-8", "openai/openai/gpt-5.2"]


# urllib honours http_proxy / https_proxy, and this box exports a proxy on a
# port with nothing listening. That turns every attempt into "Connection
# refused" regardless of the credential, which reads exactly like a bad key.
# The server itself is Node, which ignores those variables -- so the two
# disagree unless the proxy is bypassed explicitly here.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe(url: str, key: str, model: str, timeout: float = 25.0) -> tuple[bool, str]:
    payload = json.dumps({
        "model": model,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "reply with the single word ok"}],
    }).encode()
    request = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with DIRECT.open(request, timeout=timeout) as response:
            body = response.read(2000).decode("utf-8", "replace")
            try:
                text = json.loads(body)["choices"][0]["message"]["content"]
            except Exception:
                text = body[:120]
            return True, f"{response.status} -> {text.strip()[:60]!r}"
    except urllib.error.HTTPError as exc:
        detail = exc.read(400).decode("utf-8", "replace").replace("\n", " ")
        return False, f"{exc.code} {exc.reason}: {detail[:160]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def list_models(url: str, key: str, timeout: float = 25.0) -> tuple[bool, str]:
    """Ask the gateway what this key may use, rather than guessing names.

    A 403 saying "this key can only access models=[...]" means the credential
    is fine and only the model name is wrong -- which the models endpoint can
    answer directly.
    """
    base = url.split("/chat/completions")[0].rstrip("/")
    request = urllib.request.Request(
        f"{base}/models", headers={"Authorization": f"Bearer {key}"}, method="GET")
    try:
        with DIRECT.open(request, timeout=timeout) as response:
            payload = json.loads(response.read(20000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return False, f"{exc.code} {exc.reason}: {exc.read(300).decode('utf-8', 'replace')[:200]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    names = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")]
    return True, ", ".join(names) if names else json.dumps(payload)[:300]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", action="append", required=True, help="repeatable")
    parser.add_argument("--url", action="append", help="repeatable; defaults to the known NVIDIA endpoints")
    parser.add_argument("--model", action="append", help="repeatable")
    parser.add_argument("--write", help="write a gateway.env for the first working combination")
    parser.add_argument("--list", action="store_true", help="ask each endpoint which models the key may use, then stop")
    args = parser.parse_args()

    if args.list:
        for url in args.url or DEFAULT_URLS:
            print(f"\n{url.split('/chat/completions')[0]}/models")
            for key in args.key:
                ok, detail = list_models(url, key)
                print(f"  {'OK  ' if ok else '    '}{key[:6]}...{key[-4:]}  {detail}")
        return 0

    urls = args.url or DEFAULT_URLS
    models = args.model or DEFAULT_MODELS
    winner = None

    for url in urls:
        print(f"\n{url}")
        for key in args.key:
            label = f"{key[:6]}...{key[-4:]}"
            for model in models:
                ok, detail = probe(url, key, model)
                mark = "OK  " if ok else "    "
                print(f"  {mark}{label}  {model:<22} {detail}")
                if ok and winner is None:
                    winner = (url, key, model)
                if ok:
                    break            # this key works here; no need for more models
            # A 401 means the key is wrong for this endpoint, not the model, so
            # there is nothing to learn from the other endpoints for this key.

    if not winner:
        print("\nNothing answered. Either none of these keys is valid for these endpoints, "
              "or the endpoint is somewhere else entirely.")
        return 1

    url, key, model = winner
    print(f"\nworks: {model} at {url}")
    env = (
        "# Credential for the playground assistant. Contains a secret.\n"
        f"export GATEWAY_BASE_URL={url}\n"
        f"export GATEWAY_API_KEY={key}\n"
        f"export GATEWAY_MODEL={model}\n"
    )
    if args.write:
        import os
        with open(args.write, "w", encoding="utf-8") as handle:
            handle.write(env)
        try:
            os.chmod(args.write, 0o600)
        except OSError:
            pass
        print(f"wrote {args.write}")
    else:
        print("\n" + env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
