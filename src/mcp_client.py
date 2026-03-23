import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys
import json

async def fetch_projection():
    print("Initiating MCP connection to HoopsEdge Server...")
    # Path to the server script and the python executable with fastmcp installed
    python_exe = sys.executable 
    server_script = "/Users/cal/Desktop/UConn/Spring26/GRAD5900/hoops-edge/src/mcp_server.py"
    
    server_parameters = StdioServerParameters(
        command=python_exe,
        args=[server_script]
    )
    
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print("Available tools from HoopsEdge MCP:")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")
            
            # Call the projection tool for UConn (Away) vs Purdue (Home)
            print("\nCalling 'get_matchup_projection' over MCP...")
            result = await session.call_tool(
                "get_matchup_projection",
                {
                    "away_adj_o": 126.8, "away_adj_d": 92.4, "away_pace": 64.9,
                    "home_adj_o": 126.3, "home_adj_d": 94.7, "home_pace": 67.3,
                    "is_neutral_site": True
                }
            )
            print("Received Projection Content Array:\n", result.content)

if __name__ == "__main__":
    asyncio.run(fetch_projection())
