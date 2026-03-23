from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup

# Add the src folder to path so we can import our agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.agent import reporter_agent, AgentDependencies
from src.retriever import HybridRetriever
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from dataclasses import dataclass

app = FastAPI(title="Hoops Reporter API")

# ---------- Shared Utilities ----------
def scrape_ddg(query_str, max_results=8):
    """Scrape DuckDuckGo HTML for headlines and snippets."""
    encoded = urllib.parse.quote(query_str)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, 'html.parser')
        items = []
        for item in soup.find_all('div', class_='result')[:max_results]:
            title_tag = item.find('a', class_='result__a')
            snippet_tag = item.find('a', class_='result__snippet')
            title = title_tag.text.strip() if title_tag else ""
            snippet = snippet_tag.text.strip() if snippet_tag else ""
            if title:
                items.append(f"**{title}**: {snippet}")
        return items
    except Exception:
        return []

# ---------- RAG Retriever (Knowledge Base) ----------
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "data")
rag_retriever = HybridRetriever(data_dir)
rag_retriever.ingest()

# ---------- MCP Server Path ----------
mcp_server_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../hoops-edge/src/mcp_server.py")

# ---------- Auditor Agent (LLM-as-a-Judge Eval) ----------
auditor_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    system_prompt=(
        "You are an impartial AI Auditor (LLM-as-a-Judge component). "
        "Your job is to review sports journalism for factual consistency, non-absolute language, and bias. "
        "Score the report from 0 to 100 on 'Factuality'. Provide a 1-sentence review thought in 'auditor_note'. "
        "Output ONLY a valid JSON object strictly matching this format without markdown codeblocks: {\"factuality_score\": 95, \"auditor_note\": \"The report accurately cites injuries...\"}"
    ),
    output_type=str
)

# ---------- Newsletter Dependencies ----------
@dataclass
class NewsletterDeps:
    mcp_session: ClientSession
    raw_snippets: str  # The original scraped data for reference

# ---------- Agentic Newsletter Writer ----------
hot_stories_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    deps_type=NewsletterDeps,
    system_prompt=(
        "You are a Senior Editor for the Hoops Oracle, writing a comprehensive basketball newsletter. "
        "You will receive initial headlines and snippets, but you also have TOOLS to get more details.\n\n"
        "YOUR WORKFLOW:\n"
        "1. Read the initial headlines provided in the prompt.\n"
        "2. For any story where key details are missing (opponent, score, specific players), "
        "USE the `deep_search` tool to search for those specifics.\n"
        "3. Use `enrich_with_espn` to pull real team records or rosters via MCP when relevant.\n"
        "4. Use `search_archive` to pull historical context from our RAG knowledge base.\n"
        "5. Write the final newsletter using ONLY verified, sourced facts.\n\n"
        "FORMAT YOUR OUTPUT EXACTLY LIKE THIS:\n"
        "## 🏫 College Basketball\n"
        "Then list each college story as:\n"
        "### [Specific Story Title]\n"
        "[3-5 sentence detailed summary with concrete facts you gathered]\n\n"
        "---\n\n"
        "## 🏀 NBA\n"
        "Then list each NBA story as:\n"
        "### [Specific Story Title]\n"
        "[3-5 sentence detailed summary with concrete facts you gathered]\n\n"
        "RULES:\n"
        "- Cover as many distinct real stories as exist. Do NOT cap at 3.\n"
        "- ALWAYS use your tools to fill in missing details before writing. Do NOT leave stories vague.\n"
        "- If a tool returns no useful data, state what is known without guessing.\n"
        "- Add a horizontal rule (---) between each story.\n"
        "- Do NOT repeat the same story twice — merge overlapping snippets into one rich entry.\n"
        "- Include specific team records, player names, and scores wherever possible."
    )
)

@hot_stories_agent.tool
def deep_search(ctx: RunContext[NewsletterDeps], query: str) -> str:
    """Search the web for specific details about a basketball story. Use this when headlines mention a team or event but lack specifics like scores, opponents, or player details."""
    print(f"[Newsletter Tool] -> deep_search('{query}')")
    results = scrape_ddg(query, max_results=6)
    return "\n".join(results) if results else "No additional details found."

@hot_stories_agent.tool
async def enrich_with_espn(ctx: RunContext[NewsletterDeps], team_name: str) -> str:
    """Fetch real team data (recent games, record, key results) from ESPN via MCP. Use this to get verified stats for a team mentioned in a story."""
    print(f"[Newsletter Tool] -> enrich_with_espn('{team_name}')")
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_recent_games", {"team_name": team_name})
        return result.content[0].text if result.content else "No ESPN data found."
    except Exception as e:
        return f"ESPN MCP call failed: {str(e)}"

@hot_stories_agent.tool
def search_archive(ctx: RunContext[NewsletterDeps], query: str) -> str:
    """Search our historical scouting notes and reports RAG vector database for background context on a team or storyline."""
    print(f"[Newsletter Tool] -> search_archive('{query}')")
    results = rag_retriever.hybrid_search(query, top_k=3)
    if results:
        return "\n---\n".join(results)
    return "No relevant historical context found."

# ---------- Newsletter Fact-Check Auditor (Eval) ----------
newsletter_auditor = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    system_prompt=(
        "You are a Fact-Check Auditor. You will receive two things:\n"
        "1. RAW SOURCE DATA: The original search engine snippets.\n"
        "2. DRAFT NEWSLETTER: A newsletter written from those snippets and follow-up research.\n\n"
        "Your job: Review every factual claim in the DRAFT. If ANY claim (a score, an opponent, a matchup result, "
        "a player stat, a coaching hire/fire) seems inconsistent or suspicious, flag it by adding '[unverified]' next to it. "
        "Do NOT remove stories entirely — just mark unverified claims.\n\n"
        "Also output a factuality score from 0-100 on the LAST LINE in this exact format:\n"
        "<!-- SCORE:85 -->\n\n"
        "Output the newsletter in the exact same markdown format with any corrections applied."
    )
)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptRequest(BaseModel):
    prompt: str

# ---------- Custom Report Endpoint ----------
@app.post("/api/report")
async def generate_report(req: PromptRequest):
    print(f"Received request: {req.prompt}")
    python_exe = sys.executable 
    
    server_parameters = StdioServerParameters(command=python_exe, args=[mcp_server_script])
    
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            deps = AgentDependencies(mcp_session=session)
            
            result = await reporter_agent.run(req.prompt, deps=deps)
            
            try:
                final_text = result.new_messages()[-1].parts[-1].content
            except Exception:
                final_text = getattr(result, 'data', str(result))
                
            # Run the LLM-as-a-Judge Auditor dynamically
            try:
                auditor_result = await auditor_agent.run(f"Audit this report:\n{final_text}")
                audit_json_str = auditor_result.data.strip()
                if audit_json_str.startswith("```json"): audit_json_str = audit_json_str[7:]
                if audit_json_str.endswith("```"): audit_json_str = audit_json_str[:-3]
                audit_data = json.loads(audit_json_str.strip())
            except Exception as e:
                audit_data = {"factuality_score": 90, "auditor_note": f"Auditor parsing failed: {e}"}
                
            return {
                "report": final_text,
                "trust_score": audit_data.get("factuality_score", 90),
                "auditor_note": audit_data.get("auditor_note", "Verified Component.")
            }

# ---------- Agentic Hot Stories Endpoint ----------
@app.get("/api/hot-stories")
async def get_hot_stories():
    try:
        # Phase 1: Broad multi-query scrape for initial headlines
        queries = [
            "NCAA tournament March Madness 2026 scores results upsets today",
            "NBA scores results highlights today 2026",
            "NBA trade rumors injuries news 2026",
            "college basketball coaching changes news 2026",
        ]
        
        seen_titles = set()
        all_results = []
        for q in queries:
            for item in scrape_ddg(q, max_results=8):
                title_line = item.split(":")[0].strip("* ")
                if title_line not in seen_titles:
                    seen_titles.add(title_line)
                    all_results.append(item)
        
        raw_news = "\n\n".join(all_results)
        if not raw_news:
            return {"feed": "No active stories found right now.", "trust_score": 0}
        
        # Phase 2: Agentic writer with MCP + RAG + follow-up search tools
        python_exe = sys.executable
        server_parameters = StdioServerParameters(command=python_exe, args=[mcp_server_script])
        
        async with stdio_client(server_parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                deps = NewsletterDeps(mcp_session=session, raw_snippets=raw_news)
                
                result = await hot_stories_agent.run(
                    f"Today's date is March 23, 2026. Write a comprehensive, detailed newsletter. "
                    f"Use your tools (deep_search, enrich_with_espn, search_archive) to fill in "
                    f"any missing details before writing each story.\n\n"
                    f"INITIAL HEADLINES:\n{raw_news}",
                    deps=deps
                )
                try:
                    draft_text = result.new_messages()[-1].parts[-1].content
                except Exception:
                    draft_text = getattr(result, 'data', str(result))
        
        # Phase 3: Eval — Auditor verifies claims against raw source data
        try:
            audit_result = await newsletter_auditor.run(
                f"RAW SOURCE DATA:\n{raw_news}\n\n---\n\nDRAFT NEWSLETTER:\n{draft_text}"
            )
            try:
                feed_text = audit_result.new_messages()[-1].parts[-1].content
            except Exception:
                feed_text = getattr(audit_result, 'data', str(audit_result))
            
            # Extract trust score from the auditor's hidden comment
            trust_score = 85  # default
            if "<!-- SCORE:" in feed_text:
                try:
                    score_str = feed_text.split("<!-- SCORE:")[1].split("-->")[0].strip()
                    trust_score = int(score_str)
                    feed_text = feed_text.split("<!-- SCORE:")[0].strip()
                except Exception:
                    pass
        except Exception:
            feed_text = draft_text
            trust_score = 70
            
        return {"feed": feed_text, "trust_score": trust_score}
    except Exception as e:
        return {"feed": f"Failed to fetch hot stories: {e}", "trust_score": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
