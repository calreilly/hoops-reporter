import asyncio
import sys
import json
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dataclasses import dataclass, field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from dotenv import load_dotenv
from retriever import HybridRetriever
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import requests
from bs4 import BeautifulSoup
import urllib.parse

load_dotenv()

# Initialize the retriever for vector DB searches
data_dir = os.path.join(os.path.dirname(__file__), "data")
retriever = HybridRetriever(data_dir)
if not retriever.documents:
    retriever.ingest()

@dataclass
class AgentDependencies:
    mcp_session: ClientSession
    rag_sources: list = field(default_factory=list)

model = OpenAIChatModel(model_name="gpt-4o-mini")

reporter_agent = Agent(
    model=model,
    deps_type=AgentDependencies,
    system_prompt=(
        "You are an expert sports basketball analyst and reporter. "
        "Your task is to write accurate, narrative-driven scouting reports and news briefings for both College (NCAAB) and NBA basketball. "
        "You have access to these tools:\n"
        "1. `get_espn_roster`: Fetch the REAL current roster for any NCAA or NBA team from ESPN. ALWAYS use this for player names!\n"
        "2. `get_recent_games`: Fetch recent results, best wins, and worst losses from ESPN. Use this for recent form!\n"
        "3. `get_win_probability`: Get a mathematical win projection using real efficiency stats from our database.\n"
        "4. `search_live_news`: Search the web for current injury and news updates.\n"
        "5. `search_knowledge_base`: Search our historical scouting notes vector DB.\n"
        "CRITICAL INSTRUCTION: For PLAYER NAMES, you MUST use `get_espn_roster`. Never guess or hallucinate player names. "
        "For RECENT FORM, you MUST use `get_recent_games`. "
        "The win probability data comes from real efficiency metrics in our database. "
        "CRITICAL NOVEL FEATURE: You must include a distinct section titled 'The Contrarian Angle'. In this section, you must actively debate the mathematical win probability. If the math model projects Team A to win, you MUST construct a compelling argument for why Team B will pull off the upset, citing qualitative factors like recent injuries, form, or stylistic matchups found in your research. "
        "Format your report beautifully using markdown with headers and bold text."
    )
)

@reporter_agent.tool
async def get_espn_roster(ctx: RunContext[AgentDependencies], team_name: str) -> str:
    """Fetch the REAL current roster for any NCAA or NBA basketball team from ESPN. Returns player names, positions, years."""
    print(f"[Agent Tool Call] -> get_espn_roster('{team_name}')")
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_roster_espn", {"team_name": team_name})
        return result.content[0].text if result.content else "No roster found."
    except Exception as e:
        return f"ESPN roster fetch failed: {str(e)}"

@reporter_agent.tool
async def get_recent_games(ctx: RunContext[AgentDependencies], team_name: str) -> str:
    """Fetch recent game results, best wins, and worst losses for any NCAA or NBA team from ESPN."""
    print(f"[Agent Tool Call] -> get_recent_games('{team_name}')")
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_recent_games", {"team_name": team_name})
        return result.content[0].text if result.content else "No recent games found."
    except Exception as e:
        return f"ESPN schedule fetch failed: {str(e)}"

@reporter_agent.tool
async def get_win_probability(ctx: RunContext[AgentDependencies], away_name: str, home_name: str) -> str:
    """Get the mathematical win projection between two teams using real efficiency stats from our database."""
    print(f"[Agent Tool Call] -> get_win_probability('{away_name}', '{home_name}')")
    try:
        result = await ctx.deps.mcp_session.call_tool(
            "get_matchup_projection",
            {"away_team_name": away_name, "home_team_name": home_name}
        )
        return result.content[0].text if result.content else "Projection failed."
    except Exception as e:
        return f"MCP projection call failed: {str(e)}"

@reporter_agent.tool
def search_live_news(ctx: RunContext[AgentDependencies], team_name: str) -> str:
    """Search the web for current injury and news updates for a basketball team."""
    print(f"[Agent Tool Call] -> search_live_news('{team_name}')")
    try:
        query = urllib.parse.quote(f"{team_name} basketball news injury 2026")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        results = []
        for item in soup.find_all('div', class_='result')[:4]:
            title_tag = item.find('a', class_='result__a')
            snippet_tag = item.find('a', class_='result__snippet')
            title = title_tag.text.strip() if title_tag else ""
            snippet = snippet_tag.text.strip() if snippet_tag else ""
            if title or snippet:
                results.append(f"**{title}**: {snippet}")

        return "\n\n".join(results) if results else "No live news found."
    except Exception as e:
        return f"Web search failed: {str(e)}"

@reporter_agent.tool
def search_knowledge_base(ctx: RunContext[AgentDependencies], query: str) -> str:
    """Search our historical scouting notes and reports vector DB for qualitative analysis."""
    print(f"[Agent Tool Call] -> search_knowledge_base('{query}')")
    results = retriever.hybrid_search(query, top_k=3)
    if results:
        formatted = []
        for r in results:
            source_name = r["metadata"].get("source", "Unknown Document")
            ctx.deps.rag_sources.append({"source": source_name, "content": r["content"]})
            formatted.append(f"[Source: {source_name}]\n{r['content']}")
        return "\n---\n".join(formatted)
    return "No relevant articles found."


async def main():
    prompt = "Write a short paragraph previewing a potential UConn vs Marquette matchup. Include injury updates and the mathematical projection."
    print(f"\nUser Prompt: {prompt}\n")
    print("Agent is thinking...\n")

    python_exe = sys.executable
    server_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../hoops-edge/src/mcp_server.py")
    server_parameters = StdioServerParameters(command=python_exe, args=[server_script])

    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            deps = AgentDependencies(mcp_session=session)

            result = await reporter_agent.run(prompt, deps=deps)

            print("\n================ FINAL REPORT ================")
            try:
                final_message = result.new_messages()[-1]
                print(final_message.parts[-1].content)
            except Exception:
                print(getattr(result, 'data', str(result)))
            print("==============================================")

if __name__ == "__main__":
    asyncio.run(main())
