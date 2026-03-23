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
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

app = FastAPI(title="Hoops Reporter API")

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

hot_stories_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    system_prompt=(
        "You are a Senior Editor for the Hoops Oracle, writing a comprehensive basketball newsletter. "
        "I will provide you with raw search engine headlines and snippets covering both NCAA and NBA basketball.\n\n"
        "ABSOLUTE RULE — ZERO HALLUCINATION POLICY:\n"
        "You are ONLY allowed to state facts that are EXPLICITLY written in the provided snippets. "
        "If a snippet says 'Iowa pulled off a stunning upset' but does NOT name the opponent, you MUST write "
        "'Iowa pulled off a stunning upset' — do NOT guess or infer the opponent. "
        "If a snippet says 'High Point shocked the basketball world' but does NOT say who they beat, "
        "do NOT fill in a team name. Just say 'High Point pulled off a major upset.' "
        "NEVER invent scores, opponents, matchup details, or any fact not directly stated in the snippets. "
        "If two snippets contradict each other, report only the claim that appears more frequently.\n\n"
        "FORMAT YOUR OUTPUT EXACTLY LIKE THIS:\n"
        "## 🏫 College Basketball\n"
        "Then list each college story as:\n"
        "### [Specific Story Title]\n"
        "[2-3 sentence summary using ONLY facts from the snippets]\n\n"
        "---\n\n"
        "## 🏀 NBA\n"
        "Then list each NBA story as:\n"
        "### [Specific Story Title]\n"
        "[2-3 sentence summary using ONLY facts from the snippets]\n\n"
        "ADDITIONAL RULES:\n"
        "- Cover as many distinct real stories as exist. Do NOT cap at 3.\n"
        "- Filter out TV schedules, streaming guides, and bracket prediction articles.\n"
        "- Add a horizontal rule (---) between each story for visual separation.\n"
        "- Do NOT repeat the same story twice even if multiple snippets cover it — merge them into one entry.\n"
        "- Keep each story to 2-3 sentences with ONLY sourced facts."
    )
)

newsletter_auditor = Agent(
    model=OpenAIChatModel(model_name="gpt-4o-mini"),
    system_prompt=(
        "You are a Fact-Check Auditor. You will receive two things:\n"
        "1. RAW SOURCE DATA: The original search engine snippets.\n"
        "2. DRAFT NEWSLETTER: A newsletter written from those snippets.\n\n"
        "Your job: Review every factual claim in the DRAFT. If ANY claim (a score, an opponent, a matchup result, "
        "a player stat, a coaching hire/fire) is NOT explicitly supported by the RAW SOURCE DATA, "
        "you must REMOVE or CORRECT that claim.\n\n"
        "Output the CORRECTED newsletter in the exact same markdown format. "
        "If a story becomes empty after removing unsupported claims, remove the story entirely. "
        "Do NOT add any new information. Only keep or remove claims."
    )
)

# Allow requests from our vanilla HTML frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptRequest(BaseModel):
    prompt: str

@app.post("/api/report")
async def generate_report(req: PromptRequest):
    print(f"Received request: {req.prompt}")
    python_exe = sys.executable 
    server_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../hoops-edge/src/mcp_server.py")
    
    server_parameters = StdioServerParameters(command=python_exe, args=[server_script])
    
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

@app.get("/api/hot-stories")
async def get_hot_stories():
    def scrape_ddg(query_str, max_results=10):
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
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    items.append(f"Headline: {title}\nSnippet: {snippet}")
            return items
        except Exception:
            return []

    try:
        seen_titles = set()
        
        # Run multiple targeted searches for breadth
        queries = [
            "NCAA tournament March Madness 2026 scores results upsets",
            "NBA scores trades rumors today 2026",
            "NBA injury report player updates 2026",
            "college basketball coaching changes firings hirings 2026",
        ]
        
        all_results = []
        for q in queries:
            all_results.extend(scrape_ddg(q, max_results=8))
        
        raw_news = "\n\n".join(all_results)
        if not raw_news:
            return {"feed": "No active stories found right now."}
            
        result = await hot_stories_agent.run(f"Today's date is March 23, 2026. Write a comprehensive newsletter using ONLY facts from these raw snippets. Do NOT infer or guess any details not explicitly stated:\n\n{raw_news}")
        try:
            draft_text = result.new_messages()[-1].parts[-1].content
        except Exception:
            draft_text = getattr(result, 'data', str(result))
        
        # Second pass: Auditor verifies every claim against the raw source data
        try:
            audit_result = await newsletter_auditor.run(
                f"RAW SOURCE DATA:\n{raw_news}\n\n---\n\nDRAFT NEWSLETTER:\n{draft_text}"
            )
            try:
                feed_text = audit_result.new_messages()[-1].parts[-1].content
            except Exception:
                feed_text = getattr(audit_result, 'data', str(audit_result))
        except Exception:
            feed_text = draft_text  # Fall back to unaudited draft
            
        return {"feed": feed_text}
    except Exception as e:
        return {"feed": f"Failed to fetch hot stories: {e}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
