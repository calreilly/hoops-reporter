# Hoops Reporter

An Agentic RAG system that acts as an AI college basketball journalist.

This project is an entirely separate, standalone agent system that uses the **Model Context Protocol (MCP)** to securely query tools from other repositories (like connecting to the predictive mathematical models inside `hoops-edge`). 

## Features
- **Agentic RAG Pipeline:** Built with `pydantic-ai`, the Reporter Agent self-corrects and autonomously calls necessary tools.
- **Hybrid Knowledge Base:** Uses ChromaDB for Vector Semantic Search and RankBM25 for exact Keyword Search.
- **MCP Client:** Dynamically interfaces with external MCP Servers to pull live mathematical projections into its prose context.
- **LLM-as-a-Judge Eval:** Implements automated, scientific grading against a golden dataset to ensure zero hallucinations.

## Setup
1. Create a Python 3.11+ environment:
   ```bash
   uv venv --python 3.11 myvenv
   source myvenv/bin/activate
   ```
2. Install requirements:
   ```bash
   uv pip install -r requirements.txt
   ```
3. Set your `OPENAI_API_KEY` in a `.env` file at the root.

## Usage
To evaluate the agent pipeline against the golden dataset:
```bash
python src/evaluator.py
```

To run the custom reporter agent:
```bash
python src/agent.py
```
