import asyncio
import sys
import json
import os
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from dotenv import load_dotenv
from retriever import HybridRetriever
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

# Initialize Retriever (loads ChromaDB and BM25 index)
retriever = HybridRetriever("src/data")

# Setup OpenAI Model
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY is not set in the .env file.")

# pydantic_ai 1.70+ uses the env var format implicitly if OPENAI_API_KEY is set
model = OpenAIChatModel('gpt-4o-mini')

# We will pass the mcp_session in the run context dependencies.
@dataclass
class AgentDependencies:
    mcp_session: ClientSession

# Define the Agent
reporter_agent = Agent(
    model,
    deps_type=AgentDependencies,
    system_prompt=(
        "You are an expert college basketball analyst and reporter. "
        "Your task is to write accurate, narrative-driven scouting reports and news briefings. "
        "You have access to two tools: \n"
        "1. `search_knowledge_base`: Use this to find historical context, injury reports, and qualitative scouting info in our vector DB.\n"
        "2. `get_win_probability`: Use this to fetch the exact mathematical win probability and score projection between two teams using our proprietary HoopsEdge model.\n"
        "CRITICAL INSTRUCTION: You must verify your facts using `search_knowledge_base`. "
        "Always incorporate BOTH qualitative news (injuries, strategies) and quantitative win probability into your final report."
    )
)

@reporter_agent.tool
def search_knowledge_base(ctx: RunContext[AgentDependencies], query: str) -> str:
    """Retrieve articles, scouting reports, and injury updates from the vector database."""
    print(f"[Agent Tool Call] -> search_knowledge_base('{query}')")
    results = retriever.hybrid_search(query, top_k=3)
    if not results:
        return "No relevant articles found."
    return "\n\n---\n\n".join(results)


@reporter_agent.tool
async def get_win_probability(ctx: RunContext[AgentDependencies], away_name: str, home_name: str) -> str:
    """
    Project the outcome of a matchup mathematically.
    Use this to get the HoopsEdge win probability percentage and projected score.
    """
    print(f"[Agent Tool Call] -> get_win_probability('{away_name}', '{home_name}')")
    
    # We pass mock stats to the HoopsEdge server for demonstration. 
    # In a full app, the agent would use the DB to look up their actual efficiency metrics first.
    if "uconn" in away_name.lower() or "uconn" in home_name.lower():
        uconn_stats = {"adj_o": 126.8, "adj_d": 92.4, "pace": 64.9}
    else:
        uconn_stats = {"adj_o": 115.0, "adj_d": 98.0, "pace": 66.0}
        
    if "purdue" in away_name.lower() or "purdue" in home_name.lower():
        opp_stats = {"adj_o": 126.3, "adj_d": 94.7, "pace": 67.3}
    elif "marquette" in away_name.lower() or "marquette" in home_name.lower():
        opp_stats = {"adj_o": 120.5, "adj_d": 96.1, "pace": 69.1}
    else:
        opp_stats = {"adj_o": 110.0, "adj_d": 100.0, "pace": 68.0}
        
    result = await ctx.deps.mcp_session.call_tool(
        "get_matchup_projection",
        {
            "away_adj_o": uconn_stats["adj_o"], "away_adj_d": uconn_stats["adj_d"], "away_pace": uconn_stats["pace"],
            "home_adj_o": opp_stats["adj_o"], "home_adj_d": opp_stats["adj_d"], "home_pace": opp_stats["pace"],
            "is_neutral_site": True
        }
    )
    return result.content[0].text

async def main():
    print("Initiating MCP connection to HoopsEdge Server...")
    python_exe = sys.executable 
    server_script = "/Users/cal/Desktop/UConn/Spring26/GRAD5900/hoops-edge/src/mcp_server.py"
    
    server_parameters = StdioServerParameters(
        command=python_exe,
        args=[server_script]
    )
    
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            deps = AgentDependencies(mcp_session=session)
            
            prompt = "Write a short paragraph previewing a potential UConn vs Marquette matchup. Include injury updates and the mathematical projection."
            
            print(f"\nUser Prompt: {prompt}\n")
            print("Agent is thinking...\n")
            
            result = await reporter_agent.run(prompt, deps=deps)
            
            print("\n================ FINAL REPORT ================")
            if hasattr(result, 'data'):
                print(result.data)
            else:
                print(getattr(result, 'new_messages', lambda: str(result))() if hasattr(result, 'new_messages') else str(result))
            print("==============================================")

if __name__ == "__main__":
    asyncio.run(main())
