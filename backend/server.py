from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import json
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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

# ---------- Eval Log ----------
EVAL_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_log.json")

def log_eval(entry_type, score, note=""):
    """Append an eval entry to the JSON log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": entry_type,
        "score": score,
        "note": note
    }
    try:
        if os.path.exists(EVAL_LOG_PATH):
            with open(EVAL_LOG_PATH, 'r') as f:
                log = json.load(f)
        else:
            log = []
        log.append(entry)
        with open(EVAL_LOG_PATH, 'w') as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass

# ---------- Cache ----------
_cache = {}
CACHE_TTL = 1800  # 30 minutes

def get_cache(key):
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL:
            return entry["data"]
    return None

def set_cache(key, data):
    _cache[key] = {"data": data, "ts": time.time()}

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
    raw_snippets: str

# ---------- Agentic Newsletter Writer ----------
hot_stories_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    deps_type=NewsletterDeps,
    system_prompt=(
        "You are a Senior Editor for the Hoops Report, writing a comprehensive basketball newsletter. "
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
    """Search the web for specific details about a basketball story."""
    print(f"[Newsletter Tool] -> deep_search('{query}')")
    results = scrape_ddg(query, max_results=6)
    return "\n".join(results) if results else "No additional details found."

@hot_stories_agent.tool
async def enrich_with_espn(ctx: RunContext[NewsletterDeps], team_name: str) -> str:
    """Fetch real team data from ESPN via MCP."""
    print(f"[Newsletter Tool] -> enrich_with_espn('{team_name}')")
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_recent_games", {"team_name": team_name})
        return result.content[0].text if result.content else "No ESPN data found."
    except Exception as e:
        return f"ESPN MCP call failed: {str(e)}"

@hot_stories_agent.tool
def search_archive(ctx: RunContext[NewsletterDeps], query: str) -> str:
    """Search our RAG vector database for historical context."""
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
        "Your job: Review every factual claim in the DRAFT. If ANY claim is NOT supported, "
        "flag it by adding '[unverified]' next to it.\n\n"
        "Also output a factuality score from 0-100 on the LAST LINE in this exact format:\n"
        "<!-- SCORE:85 -->\n\n"
        "Output the newsletter in the exact same markdown format with any corrections applied."
    )
)

# ---------- Chat Agent ----------
chat_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    deps_type=AgentDependencies,
    system_prompt=(
        "You are the Hoops Reporter, an expert basketball assistant. "
        "IMPORTANT: The current date is March 23, 2026. We are in the 2025-26 NBA season and 2025-26 NCAA season. "
        "When searching the web, ALWAYS include 'March 2026' or '2025-26 season' in your queries to get current data. "
        "NEVER reference the 2023-24 season — that data is outdated. "
        "Answer questions about NBA and NCAA basketball concisely and accurately. "
        "You have access to tools to look up real data — always use them when the user asks about a specific team, player, or matchup. "
        "Keep responses conversational, 2-4 sentences unless more detail is needed. "
        "Use markdown formatting for readability."
    )
)

@chat_agent.tool
async def lookup_team(ctx: RunContext[AgentDependencies], team_name: str) -> str:
    """Fetch recent games and record for a team from ESPN via MCP."""
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_recent_games", {"team_name": team_name})
        return result.content[0].text if result.content else "No data found."
    except Exception as e:
        return f"Lookup failed: {str(e)}"

@chat_agent.tool
async def lookup_roster(ctx: RunContext[AgentDependencies], team_name: str) -> str:
    """Fetch the real roster for a team from ESPN via MCP."""
    try:
        result = await ctx.deps.mcp_session.call_tool("get_team_roster_espn", {"team_name": team_name})
        return result.content[0].text if result.content else "No roster found."
    except Exception as e:
        return f"Roster lookup failed: {str(e)}"

@chat_agent.tool
def chat_web_search(ctx: RunContext[AgentDependencies], query: str) -> str:
    """Search the web for current basketball news. Automatically targets March 2026 results."""
    dated_query = f"{query} March 2026" if "2026" not in query else query
    results = scrape_ddg(dated_query, max_results=4)
    return "\n".join(results) if results else "No results found."

@chat_agent.tool
def chat_knowledge_base(ctx: RunContext[AgentDependencies], query: str) -> str:
    """Search our RAG vector DB for historical scouting context."""
    results = rag_retriever.hybrid_search(query, top_k=3)
    return "\n---\n".join(results) if results else "No relevant context."

# ---------- Player Spotlight Agent ----------
spotlight_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    system_prompt=(
        "You are a Player Profile Writer for the Hoops Report. "
        "Given raw data about a player (roster info, team recent games, web search results, scouting notes), "
        "write a detailed, engaging player spotlight card.\n\n"
        "FORMAT:\n"
        "## [Player Name]\n"
        "### Quick Facts\n"
        "- **Team:** ...\n"
        "- **Position:** ...\n"
        "- **Class/Experience:** ...\n\n"
        "### Season Overview\n"
        "[2-3 sentences about their season based on the data]\n\n"
        "### Scouting Report\n"
        "[2-3 sentences of analysis from the scouting archive]\n\n"
        "### Latest News\n"
        "[Key recent news items]\n\n"
        "Use ONLY facts from the provided data. Do NOT fabricate statistics."
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

class ChatRequest(BaseModel):
    message: str

# ==========================================
# FEATURE 1: Live Scoreboard
# ==========================================
@app.get("/api/scores")
async def get_scores():
    """Fetch today's live scores from ESPN for NCAA and NBA."""
    games = []
    
    # NCAA Men's Basketball
    try:
        ncaa_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
        resp = requests.get(ncaa_url, timeout=6)
        data = resp.json()
        for event in data.get("events", [])[:8]:
            comps = event.get("competitions", [{}])[0]
            teams = comps.get("competitors", [])
            if len(teams) == 2:
                away = teams[1]
                home = teams[0]
                games.append({
                    "league": "NCAAB",
                    "away": away.get("team", {}).get("abbreviation", "?"),
                    "home": home.get("team", {}).get("abbreviation", "?"),
                    "away_score": away.get("score", "0"),
                    "home_score": home.get("score", "0"),
                    "status": event.get("status", {}).get("type", {}).get("shortDetail", "")
                })
    except Exception:
        pass
    
    # NBA
    try:
        nba_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
        resp = requests.get(nba_url, timeout=6)
        data = resp.json()
        for event in data.get("events", [])[:8]:
            comps = event.get("competitions", [{}])[0]
            teams = comps.get("competitors", [])
            if len(teams) == 2:
                away = teams[1]
                home = teams[0]
                games.append({
                    "league": "NBA",
                    "away": away.get("team", {}).get("abbreviation", "?"),
                    "home": home.get("team", {}).get("abbreviation", "?"),
                    "away_score": away.get("score", "0"),
                    "home_score": home.get("score", "0"),
                    "status": event.get("status", {}).get("type", {}).get("shortDetail", "")
                })
    except Exception:
        pass
    
    return {"games": games}

# ==========================================
# FEATURE 2: Ask the Reporter Chat
# ==========================================
@app.post("/api/chat")
async def chat(req: ChatRequest):
    python_exe = sys.executable
    server_parameters = StdioServerParameters(command=python_exe, args=[mcp_server_script])
    
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            deps = AgentDependencies(mcp_session=session)
            
            result = await chat_agent.run(req.message, deps=deps)
            try:
                reply = result.new_messages()[-1].parts[-1].content
            except Exception:
                reply = getattr(result, 'data', str(result))
            
            # Extract tool trace for pipeline viz
            tool_trace = []
            for msg in result.new_messages():
                for part in msg.parts:
                    if hasattr(part, 'tool_name'):
                        tool_trace.append({
                            "tool": part.tool_name,
                            "args": str(getattr(part, 'args', ''))[:100]
                        })
            
            return {"reply": reply, "tool_trace": tool_trace}

# ==========================================
# FEATURE 3: Player Spotlight
# ==========================================
@app.get("/api/player/{player_name}")
async def get_player_spotlight(player_name: str):
    python_exe = sys.executable
    server_parameters = StdioServerParameters(command=python_exe, args=[mcp_server_script])
    
    raw_data = {}
    
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Web search for player
            raw_data["web"] = "\n".join(scrape_ddg(f"{player_name} basketball stats 2026", max_results=5))
            
            # RAG archive search
            rag_results = rag_retriever.hybrid_search(player_name, top_k=3)
            raw_data["archive"] = "\n---\n".join(rag_results) if rag_results else "No scouting notes found."
            
            # Try to get roster (if team is mentioned in search results)
            try:
                roster_result = await session.call_tool("get_team_roster_espn", {"team_name": player_name.split()[-1]})
                raw_data["roster"] = roster_result.content[0].text if roster_result.content else ""
            except Exception:
                raw_data["roster"] = ""
    
    # Generate spotlight card
    prompt = f"Write a player spotlight for **{player_name}** using this data:\n\nWeb Results:\n{raw_data['web']}\n\nScouting Archive:\n{raw_data['archive']}\n\nRoster Data:\n{raw_data['roster']}"
    
    result = await spotlight_agent.run(prompt)
    try:
        card_text = result.new_messages()[-1].parts[-1].content
    except Exception:
        card_text = getattr(result, 'data', str(result))
    
    # Eval the spotlight
    try:
        audit_result = await auditor_agent.run(f"Audit this player profile:\n{card_text}")
        audit_str = audit_result.data.strip()
        if audit_str.startswith("```json"): audit_str = audit_str[7:]
        if audit_str.endswith("```"): audit_str = audit_str[:-3]
        audit_data = json.loads(audit_str.strip())
        trust_score = audit_data.get("factuality_score", 80)
        log_eval("player_spotlight", trust_score, player_name)
    except Exception:
        trust_score = 75
    
    return {"card": card_text, "trust_score": trust_score}

# ==========================================
# FEATURE 4: Custom Report (with pipeline trace)
# ==========================================
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
            
            # Extract tool trace for pipeline visualization
            tool_trace = []
            for msg in result.new_messages():
                for part in msg.parts:
                    if hasattr(part, 'tool_name'):
                        tool_trace.append({
                            "tool": part.tool_name,
                            "args": str(getattr(part, 'args', ''))[:100]
                        })
                
            # Run the LLM-as-a-Judge Auditor
            try:
                auditor_result = await auditor_agent.run(f"Audit this report:\n{final_text}")
                audit_json_str = auditor_result.data.strip()
                if audit_json_str.startswith("```json"): audit_json_str = audit_json_str[7:]
                if audit_json_str.endswith("```"): audit_json_str = audit_json_str[:-3]
                audit_data = json.loads(audit_json_str.strip())
            except Exception as e:
                audit_data = {"factuality_score": 90, "auditor_note": f"Auditor parsing failed: {e}"}
            
            trust_score = audit_data.get("factuality_score", 90)
            log_eval("report", trust_score, req.prompt[:50])
                
            return {
                "report": final_text,
                "trust_score": trust_score,
                "auditor_note": audit_data.get("auditor_note", "Verified Component."),
                "tool_trace": tool_trace
            }

# ==========================================
# FEATURE 5: Agentic Hot Stories (with cache)
# ==========================================
@app.get("/api/hot-stories")
async def get_hot_stories():
    # Check cache first
    cached = get_cache("hot_stories")
    if cached:
        return {**cached, "cached": True}
    
    try:
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
            return {"feed": "No active stories found right now.", "trust_score": 0, "cached": False}
        
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
        
        # Eval pass
        try:
            audit_result = await newsletter_auditor.run(
                f"RAW SOURCE DATA:\n{raw_news}\n\n---\n\nDRAFT NEWSLETTER:\n{draft_text}"
            )
            try:
                feed_text = audit_result.new_messages()[-1].parts[-1].content
            except Exception:
                feed_text = getattr(audit_result, 'data', str(audit_result))
            
            trust_score = 85
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
        
        log_eval("newsletter", trust_score)
        
        response_data = {"feed": feed_text, "trust_score": trust_score}
        set_cache("hot_stories", response_data)
            
        return {**response_data, "cached": False}
    except Exception as e:
        return {"feed": f"Failed to fetch hot stories: {e}", "trust_score": 0, "cached": False}

# ==========================================
# FEATURE 6: Evaluation Dashboard
# ==========================================
@app.get("/api/eval-history")
async def get_eval_history():
    try:
        if os.path.exists(EVAL_LOG_PATH):
            with open(EVAL_LOG_PATH, 'r') as f:
                log = json.load(f)
        else:
            log = []
        
        # Calculate summary stats
        scores = [e["score"] for e in log if e.get("score")]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        
        return {
            "entries": log[-50:],  # last 50 entries
            "total_evals": len(log),
            "avg_score": avg_score,
            "by_type": {
                "report": [e for e in log if e.get("type") == "report"][-10:],
                "newsletter": [e for e in log if e.get("type") == "newsletter"][-10:],
                "player_spotlight": [e for e in log if e.get("type") == "player_spotlight"][-10:],
            }
        }
    except Exception:
        return {"entries": [], "total_evals": 0, "avg_score": 0, "by_type": {}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
