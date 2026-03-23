import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def llm_as_a_judge(question: str, context: str, answer: str) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    
    prompt = f"""
    You are an impartial judge evaluating a sports reporter's answer.
    
    Given the following Context, evaluate the Faithfulness of the Answer.
    The Answer is faithful if it contains NO hallucinated information that is absent from the Context.
    
    Context: {context}
    
    Answer: {answer}
    
    Return a score from 0.0 to 1.0 (where 1.0 is completely faithful) and a short justification, in the format:
    SCORE: <score>
    REASON: <reason>
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    
    return response.choices[0].message.content

def run_evaluation():
    print("Initiating Custom 'LLM-as-a-Judge' Evaluation Pipeline...")
    
    questions = [
        "What is the injury status of Purdue's Braden Smith?",
        "How did UConn's Donovan Clingan perform against Marquette?"
    ]
    
    contexts = [
        "Purdue's Braden Smith suffered a minor ankle sprain during practice this week, but head coach Matt Painter says he is day-to-day and expected to play in the Sweet 16.",
        "Donovan Clingan logged a season-high 18 rebounds in a physical matchup against Marquette last week."
    ]
    
    answers = [
        "Smith suffered a severe ACL tear and is out for the season.", # Intentional hallucination to test the judge
        "Donovan Clingan dominated with 18 rebounds." # Faithful
    ]
    
    for i, (q, c, a) in enumerate(zip(questions, contexts, answers)):
        print(f"\n[EVALUATION {i+1}]")
        print(f"Question: {q}")
        print(f"Agent's Answer: {a}")
        print("--- Judge Score ---")
        verdict = llm_as_a_judge(q, c, a)
        print(verdict)

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set OPENAI_API_KEY to run the LLM-as-a-judge evaluator.")
    else:
        run_evaluation()
