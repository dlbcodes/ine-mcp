"""
test_client.py — calls the MCP server's tool directly, in-process.

No terminal juggling, no separate running server: Client(mcp) connects
straight to the server object from main.py. This is the same pattern
the SDK's own testing docs use.
"""

import asyncio
from mcp import Client
from main import mcp


async def main():
    async with Client(mcp) as client:
        # Test 1: search the catalogue for something crime-related
        search_result = await client.call_tool(
            "search_indicators", {"query": "criminalidade"}
        )
        print("--- search_indicators ---")
        print(search_result.content[0].text)

        # Test 2: fetch metadata for that same indicator — this is the
        # piece that tells us what dim1/dim2 codes are actually valid
        meta_result = await client.call_tool(
            "get_metadata", {"varcd": "0008074"}
        )
        print("\n--- get_metadata ---")
        print(meta_result.content[0].text)

        # Test 3: resolve human keywords into real dimension codes —
        # instead of us knowing "20" means Açores by heart
        resolve_result = await client.call_tool(
            "resolve_dimensions",
            {"varcd": "0008074", "filters": {"2": "Açores", "3": "Total"}},
        )
        print("\n--- resolve_dimensions ---")
        print(resolve_result.content[0].text)

        # Test 4: fetch a known indicator's data
        data_result = await client.call_tool(
            "get_indicator",
            {"varcd": "0008074", "dim1": "S7A2015", "dim2": "20"},
        )
        print("\n--- get_indicator ---")
        print(data_result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())