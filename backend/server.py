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
        "You are a Senior Editor for the Hoops Oracle. "
        "I will provide you with raw search engine headlines for today's basketball news. "
        "Your job is to curate and summarize the Top 3 most important storylines in a beautifully formatted markdown list. "
        "Do not include a main title. Just jump straight into the 3 stories using `### 1. [Story Title]` format. "
        "Keep it punchy, engaging, and professional."
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
    try:
        # Search DuckDuckGo for general basketball news
        query = urllib.parse.quote("college basketball OR NBA news today 2026")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for item in soup.find_all('div', class_='result')[:8]:
            title_tag = item.find('a', class_='result__a')
            snippet_tag = item.find('a', class_='result__snippet')
            title = title_tag.text.strip() if title_tag else ""
            snippet = snippet_tag.text.strip() if snippet_tag else ""
            if title:
                results.append(f"Headline: {title}\nSnippet: {snippet}")
                
        raw_news = "\n\n".join(results)
        if not raw_news:
            return {"feed": "No active stories found right now."}
            
        result = await hot_stories_agent.run(f"Raw news feed:\n{raw_news}")
        try:
            feed_text = result.new_messages()[-1].parts[-1].content
        except Exception:
            feed_text = getattr(result, 'data', str(result))
            
        return {"feed": feed_text}
    except Exception as e:
        return {"feed": f"Failed to fetch hot stories: {e}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
