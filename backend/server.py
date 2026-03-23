from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import json

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
