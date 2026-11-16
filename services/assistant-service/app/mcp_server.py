"""
Ajanda MCP sunucusu (Faz 13i): Claude Desktop / Claude Code'a stdio uzerinden arac olur.

    uv run --directory <assistant-service klasoru> python -m app.mcp_server

Ortam: AJANDA_TOKEN (zorunlu erisim anahtari), AJANDA_TASK_API_URL (istege bagli).
`stdout` yalniz MCP protokolune aittir: log `stderr`e gider.
"""

import asyncio
import logging
import os
import sys

from mcp import types
from mcp.server import Server, ServerRequestContext

from app.config import settings
from app.db.models import session_maker
from app.mcp_tools import ENGLISH_PROMPT, McpBridge, english_prompt_text


def build_server(bridge: McpBridge) -> Server:
    async def on_list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        tools = await bridge.list_tools()
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=t.name, description=t.description, inputSchema=t.input_schema
                )
                for t in tools
            ]
        )

    async def on_call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        reply = await bridge.call(params.name, params.arguments or {})
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=reply.text)],
            is_error=reply.is_error,
        )

    async def on_list_prompts(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListPromptsResult:
        return types.ListPromptsResult(
            prompts=[
                types.Prompt(
                    name=ENGLISH_PROMPT,
                    description="Ajanda İngilizce koçu verileriyle derin pratik seansı",
                    arguments=[
                        types.PromptArgument(
                            name="minutes",
                            description="Seans süresi (dakika, varsayılan 20)",
                            required=False,
                        )
                    ],
                )
            ]
        )

    async def on_get_prompt(
        ctx: ServerRequestContext, params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        if params.name != ENGLISH_PROMPT:
            raise ValueError(f"Bilinmeyen prompt: {params.name}")
        text = english_prompt_text((params.arguments or {}).get("minutes"))
        return types.GetPromptResult(
            description="İngilizce derin pratik seansı",
            messages=[
                types.PromptMessage(
                    role="user", content=types.TextContent(type="text", text=text)
                )
            ],
        )

    return Server(
        "ajanda",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_prompts=on_list_prompts,
        on_get_prompt=on_get_prompt,
    )


async def serve(bridge: McpBridge) -> None:
    from mcp.server.stdio import stdio_server

    server = build_server(bridge)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    token = os.environ.get("AJANDA_TOKEN", "").strip()
    if not token:
        logging.getLogger(__name__).error(
            "AJANDA_TOKEN yok: Ajanda → Ayarlar → Claude bağlantısı'ndan anahtar üret."
        )
        raise SystemExit(2)
    url = os.environ.get("AJANDA_TASK_API_URL", "").strip()
    if url:
        settings.task_api_url = url
    asyncio.run(serve(McpBridge(session_maker, token)))


if __name__ == "__main__":
    main()
