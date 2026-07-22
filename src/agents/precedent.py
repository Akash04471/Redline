from pydantic import BaseModel
import json
import time
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_HISTORICAL, FAULT_INJECTION
from src.engine.audit import append_entry

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

class PrecedentOutput(BaseModel):
    similarity_score: float
    is_standard: bool
    deviation_notes: str
    confidence: float
    reasoning: str

def retrieve_historical_precedents(clause_category: str, query: str) -> str:
    """
    Retrieve historical precedents for a specific clause category.
    
    Args:
        clause_category: The category of the clause (e.g., "Indemnification", "Termination").
        query: The specific clause or concept to search for.
    """
    client = get_qdrant_client()
    query_vector = get_embedding(query)
    
    category_filter = Filter(
        must=[
            FieldCondition(key="clause_category", match=MatchValue(value=clause_category))
        ]
    )
    
    search_result = client.query_points(
        collection_name=COLLECTION_HISTORICAL,
        query=query_vector,
        query_filter=category_filter,
        limit=2
    ).points
    
    citations = [f"Accepted Precedent [{res.payload.get('status')}]: {res.payload.get('clause_text', '')}" for res in search_result]
    return "\\n".join(citations)

def precedent_agent(clause_text: str, clause_category: str, clause_id: str = "unknown") -> dict:
    """
    Agent for Precedent comparison.
    Role: Senior Legal Analyst
    """
    try:
        # FAULT INJECTION GATEWAY
        fault_mode = FAULT_INJECTION.get("precedent")
        if fault_mode == "crash":
            raise RuntimeError("Simulated agent crash.")
        elif fault_mode == "timeout":
            time.sleep(1)
            raise TimeoutError("Simulated timeout.")
        elif fault_mode == "malformed":
            raise ValueError("Simulated malformed JSON output.")

        # 1. Define Agent using ADK
        agent = LlmAgent(
            name="precedent_agent",
            model="gemini-2.5-flash",
            instruction=(
                "You are a Senior Legal Analyst. Compare the provided clause against historical precedents. "
                "Determine if it is standard or deviates materially. "
                "You must output strictly as JSON matching the PrecedentOutput schema."
            ),
            tools=[retrieve_historical_precedents],
            output_schema=PrecedentOutput.model_json_schema()
        )
        
        # 2. Setup Session and Runner
        session_service = InMemorySessionService()
        runner = Runner(agent=agent, session_service=session_service, app_name="redline_engine")
        
        last_error = None
        for attempt in range(2):
            try:
                # 3. Execute ADK Call
                prompt = (
                    f"Clause to analyze:\\n{clause_text}\\n\\n"
                    f"Clause Category: {clause_category}\\n\\n"
                    "Please use your tools to retrieve the historical precedents for this clause category, "
                    "then compare the clause and output a JSON object."
                )
                
                sess_id = session_service.create_session("system").id
                response = runner.run(
                    user_id="system",
                    session_id=sess_id,
                    new_message=prompt
                )
                
                output_text = response.text
                if not output_text:
                    raise ValueError("Empty response from LLM")
                    
                parsed_json = json.loads(output_text)
                validated_output = PrecedentOutput(**parsed_json)
                output_dict = validated_output.model_dump()
                
                # Append to audit log
                append_entry("agent_verdict", {
                    "agent": "precedent",
                    "clause_id": clause_id,
                    "clause_text": clause_text,
                    "clause_category": clause_category,
                    "output": output_dict
                })
                
                return output_dict
                
            except Exception as e:
                last_error = f"ADK Error: {e}"
                
        raise Exception(f"Failed after 2 attempts. Last error: {last_error}")

    except Exception as e:
        output_dict = {
            "agent_failed": True,
            "similarity_score": 0.0,
            "is_standard": False,
            "deviation_notes": "Unknown",
            "confidence": 0.0,
            "reasoning": f"Agent failed: {str(e)}"
        }
        append_entry("agent_verdict", {
            "agent": "precedent",
            "clause_id": clause_id,
            "clause_text": clause_text,
            "clause_category": clause_category,
            "output": output_dict
        })
        return output_dict
