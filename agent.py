"""
agent.py — a minimal agent loop: Claude decides which of our MCP
tools to call, we run them locally, feed results back, repeat.

This recreates what Claude Desktop does, without installing it.
Needs an Anthropic API key: https://console.anthropic.com

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 agent.py "Give me the evolution of crime rates in Porto over the last 10 years"
"""

import asyncio
import os
import sys
import requests
from mcp import Client
from main import mcp

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"


def mcp_tool_to_anthropic_schema(tool) -> dict:
    """Convert an MCP tool's schema into the shape Anthropic's API
    expects for tool-use. They're both JSON Schema underneath, so
    this is mostly a rename."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


async def run_agent(question: str):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY first: export ANTHROPIC_API_KEY='sk-ant-...'")
        return

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with Client(mcp) as client:
        # Discover our own tools' schemas automatically, rather than
        # retyping them by hand — this is the same list the MCP
        # protocol would hand to any real client.
        tool_list = await client.list_tools()
        anthropic_tools = [mcp_tool_to_anthropic_schema(t) for t in tool_list.tools]

        messages = [{"role": "user", "content": question}]

        while True:
            resp = requests.post(
                API_URL,
                headers=headers,
                json={
                    "model": MODEL,
                    "max_tokens": 1024,
                    "messages": messages,
                    "tools": anthropic_tools,
                },
                timeout=60,
            )
            if resp.status_code >= 400:
                print(f"API error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            data = resp.json()

            messages.append({"role": "assistant", "content": data["content"]})

            tool_uses = [b for b in data["content"] if b["type"] == "tool_use"]

            if not tool_uses:
                # No more tool calls — print whatever text Claude wrote
                for block in data["content"]:
                    if block["type"] == "text":
                        print(block["text"])
                return

            # Run each requested tool for real, locally
            tool_results = []
            for call in tool_uses:
                print(f"  [calling {call['name']}({call['input']})]")
                result = await client.call_tool(call["name"], call["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": result.content[0].text,
                })

            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agent.py \"your question here\"")
    else:
        asyncio.run(run_agent(sys.argv[1]))