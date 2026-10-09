"""``vsa-chat``: DeepSeek (or another function-calling model) using the MCP tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from vsa_commerce.catalog.store import CatalogStore, default_data_dir
from vsa_commerce.channels.assistant import Assistant, Reply
from vsa_commerce.channels.bridge import McpBridge
from vsa_commerce.channels.llm import LLMSettings, MissingApiKeyError, OpenAICompatibleChat
from vsa_commerce.channels.mcp_server import build_server
from vsa_commerce.tools import CommerceTools
from vsa_commerce.tracking import JsonlEventLog

ROOT = default_data_dir().parent


def read_script(path: Path) -> list[list[str]]:
    """One message per line; a blank line starts a new conversation."""
    conversations: list[list[str]] = [[]]
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith("#"):
            continue
        if not text:
            if conversations[-1]:
                conversations.append([])
            continue
        conversations[-1].append(text)
    return [c for c in conversations if c]


def format_call(name: str, arguments: dict[str, object]) -> str:
    shown = {k: v for k, v in arguments.items() if k != "session_id"}
    return f"{name}({', '.join(f'{k}={json.dumps(v, ensure_ascii=False)}' for k, v in shown.items())})"


class Transcript:
    def __init__(self, title: str) -> None:
        self.lines = [f"# {title}", ""]

    def turn(self, user: str, reply: Reply) -> None:
        self.lines += [f"**User:** {user}", ""]
        for t in reply.tools_used:
            self.lines.append(f"> tool: `{format_call(t.name, t.arguments)}`" + ("" if t.ok else " (error)"))
        if reply.tools_used:
            self.lines.append("")
        self.lines += [f"**Assistant:** {reply.text}", "", "---", ""]

    def save(self, directory: Path, name: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{name}.md"
        path.write_text("\n".join(self.lines), encoding="utf-8")
        return path


async def run(args: argparse.Namespace) -> int:
    try:
        settings = LLMSettings.from_env(model=args.model, base_url=args.base_url)
    except MissingApiKeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    backend = OpenAICompatibleChat(settings)
    store = CatalogStore(args.data_dir or default_data_dir())
    tools = CommerceTools(store, args.business, events=JsonlEventLog(args.events))
    server = build_server(tools, channel=args.channel)
    mode = "baseline" if args.no_tools else "tools"
    transcript = Transcript(f"{settings.model} via {settings.base_url}, {mode}, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC")

    async def conversation(messages: list[str] | None) -> None:
        bridge = None if args.no_tools else McpBridge(server)
        if bridge:
            await bridge.__aenter__()
        try:
            assistant = Assistant(
                backend, bridge, instructions=None if args.no_tools else server.instructions, now=datetime.now(UTC)
            )
            for user in messages if messages is not None else _prompt():
                print(f"\nYou: {user}")
                reply = await assistant.send(user)
                for t in reply.tools_used:
                    print(f"  -> {format_call(t.name, t.arguments)}" + ("" if t.ok else "  [error]"))
                print(f"\nAssistant: {reply.text}")
                transcript.turn(user, reply)
        finally:
            if bridge:
                await bridge.__aexit__(None, None, None)

    if args.script:
        for messages in read_script(args.script):
            print("\n" + "=" * 72)
            await conversation(messages)
    else:
        print(f"{settings.model} ({mode}). Empty line or Ctrl+C to quit.")
        await conversation(None)

    if args.save:
        print(f"\nTranscript: {transcript.save(args.save, mode)}")
    return 0


def _prompt() -> Iterator[str]:
    while True:
        try:
            text = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            return
        yield text


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Chat with a function-calling model over the commerce tools.")
    parser.add_argument("--business", default="victory-skating")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=ROOT / "var" / "events.jsonl")
    parser.add_argument("--channel", default="deepseek", help="label recorded with every event")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--no-tools", action="store_true", help="same model without tools: the baseline")
    parser.add_argument("--script", type=Path, default=None)
    parser.add_argument("--save", type=Path, nargs="?", const=ROOT / "var" / "transcripts", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, stream=sys.stderr)
    if not args.verbose:
        # rejected tool calls are already shown as [error]; the server's own warning would duplicate it
        logging.getLogger("fastmcp").setLevel(logging.ERROR)
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
