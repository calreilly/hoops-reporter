# Hoops Reporter

An Agentic RAG system that acts as an AI basketball journalist. 

This project explores an end-to-end LLM application leveraging the **Model Context Protocol (MCP)**, **Retrieval-Augmented Generation (RAG)**, and **LLM-as-a-judge Evaluations**. The system autonomously writes scouting reports, interfaces with live internet tools, and operates transparently so users can inspect its pipelines and citations.

## ✨ Features

- **Agentic RAG Pipeline (`pydantic-ai`)**: The Reporter Agent self-corrects and autonomously routes between vector search, live web search, and data APIs depending on the user's prompt.
- **RAG Source Transparency**: Every generation explicitly returns the document chunks it used. The UI allows users to view citations inline so that the AI's grounding is fully transparent.
- **Dynamic Knowledge Base Manager**: A dedicated interface to chunk, embed, and ingest custom scouting reports or news articles into the vector database on the fly—no server restarts required.
- **MCP Client**: Dynamically interfaces with an external MCP Server (`hoops-edge`) to pull sophisticated mathematical simulation and projection data directly into its prose context.
- **Automated Ragas-Style Evaluation Suite**: A built-in batch evaluator that uses an independent LLM-as-a-judge to grade the RAG pipeline on 4 critical metrics: *Context Precision, Context Recall, Faithfulness,* and *Answer Relevance*.
- **Pipeline Visualization**: The web UI automatically traps and visualizes the sequential `tool_trace` of the agent so users can see exactly what API calls the LLM made under the hood.

---

## 🚀 Setup & Installation

1. **Create an environment** (Python 3.11+ recommended):
   ```bash
   uv venv --python 3.11 myvenv
   source myvenv/bin/activate
   ```

2. **Install requirements**:
   ```bash
   uv pip install -r requirements.txt
   ```

3. **Environment Variables**:
   Create a `.env` file at the root of the project and add your OpenAI Key (used for embeddings and the core logic):
   ```plaintext
   OPENAI_API_KEY=sk-...
   ```

4. **Bootstrap the RAG Database** (Optional but Recommended):
   We provide a script to automatically download Wikipedia histories for over 30+ top NCAA Men's Basketball programs and ingest them into the knowledge base:
   ```bash
   python src/batch_seed.py
   ```

---

## 📖 Usage Tutorial

The application is built on a **FastAPI** backend and a **Vanilla JS/HTML/CSS** frontend.

### 1. Start the Application
Instead of starting the backend and frontend separately, you can use the provided shell script to launch both simultaneously:
```bash
bash run_app.sh
```
*This starts the FastAPI server on `http://127.0.0.1:8000` and the Frontend UI on `http://localhost:8080`.*

### 2. Navigating the App

When you open `http://localhost:8080`, you'll see a navigation bar with several powerful views:

* **📰 Hot Stories**: 
  A live ticker of recent basketball news powered by DuckDuckGo scraping, summarized by the Editor Agent, and passed through an Auditor Agent to rate factuality (indicated by the Trust Badge).

* **✍️ Reporter (New Assignment)**: 
  Give the agent a complex assignment (e.g., *"Write a preview for a potential UConn vs Marquette matchup. Include injury updates and the mathematical projection."*). 
  - The AI will draft a full markdown report.
  - Click **"🔧 Show Agent Pipeline"** at the bottom to see the exact sequence of tools it called (e.g., hitting the MCP server, querying the ChromaDB vector store, etc.).

* **💬 Ask the Reporter**: 
  A conversational interface to query the Agent. 
  - *Try asking: "Where is Donovan Clingan currently playing?"*
  - The AI will hit the vector database, generate an answer, and you can click **"📚 View RAG Sources"** to inspect the exact citations it used to prevent hallucinations.

* **⭐ Player Spotlight**: 
  Enter a player's name to generate an in-depth scouting report card. This flow integrates ESPN APIs for live stats, RAG for background intel, and assigns a Trust Score to the final output.

* **📚 Knowledge Base**: 
  The control center for the active vector database corpus. 
  - **To teach the AI something new:** Paste the content of an article, give it a title, and click "Ingest & Embed". 
  - **Auto-Scrape URL:** Paste a URL, check the box, and the backend will scrape the text and vectorize it into ChromaDB, making it immediately available for future queries!

* **📊 Analytics**: 
  View historical Trust Scores for all AI generations. 
  - To test the RAG health, click **"Run Batch Eval"**. This triggers the Ragas-style evaluation suite, which will spin up the LLM judge, execute test queries, and populate the telemetry cards *(Precision, Recall, Faithfulness, Relevance)*.
