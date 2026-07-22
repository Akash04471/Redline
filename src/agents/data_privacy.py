from pydantic import BaseModel
import json
import time
from qdrant_client.models import Filter, FieldCondition, MatchAny
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_COMPLIANCE, FAULT_INJECTION
from src.engine.audit import append_entry

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

class DataPrivacyOutput(BaseModel):
    privacy_risk_level: str  # "Low", "Medium", "High", "Critical"
    cross_border_transfer_flag: bool
    missing_safeguards: list[str]
    confidence: float
    reasoning: str

def retrieve_data_privacy_policies(query: str) -> str:
    """
    Retrieve data privacy policies (GDPR, CCPA, etc.) from the database.
    
    Args:
        query: The specific clause or concept to search for.
    """
    client = get_qdrant_client()
    query_vector = get_embedding(query)
    
    privacy_filter = Filter(
        must=[
            FieldCondition(
                key="regulation_type",
                match=MatchAny(any=["GDPR", "CCPA", "data_privacy", "Standard Data Protection"])
            )
        ]
    )
    
    search_result = client.query_points(
        collection_name=COLLECTION_COMPLIANCE,
        query=query_vector,
        query_filter=privacy_filter,
        limit=3
    ).points
    
    citations = [res.payload.get("policy_text", "") for res in search_result]
    return "\\n".join(citations)

def data_privacy_agent(clause_text: str, clause_id: str = "unknown") -> dict:
    """
    Agent for Data Privacy checking (Role: Data Protection Officer).
    """
    try:
        # FAULT INJECTION GATEWAY
        fault_mode = FAULT_INJECTION.get("data_privacy")
        if fault_mode == "crash":
            raise RuntimeError("Simulated agent crash.")
        elif fault_mode == "timeout":
            time.sleep(1)
            raise TimeoutError("Simulated timeout.")
        elif fault_mode == "malformed":
            raise ValueError("Simulated malformed JSON output.")
            
        # 1. Define Agent using ADK
        agent = LlmAgent(
            name="data_privacy_agent",
            model="gemini-2.5-flash",
            instruction=(
                "You are a Data Protection Officer (DPO). Analyze the clause against privacy-by-design "
                "principles (cross-border transfers, data minimization, retention, breach notification, "
                "subject access rights). Identify missing safeguards. "
                "You must output strictly as JSON matching the DataPrivacyOutput schema."
            ),
            tools=[retrieve_data_privacy_policies],
            output_schema=DataPrivacyOutput.model_json_schema()
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
                    "Please use your tools to retrieve the privacy policies, "
                    "then analyze the clause and output a JSON object."
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
                validated_output = DataPrivacyOutput(**parsed_json)
                output_dict = validated_output.model_dump()
                
                append_entry("agent_verdict", {
                    "agent": "data_privacy",
                    "clause_id": clause_id,
                    "clause_text": clause_text,
                    "output": output_dict
                })
                
                return output_dict
                
            except Exception as e:
                last_error = f"ADK Error: {e}"
                
        raise Exception(f"Failed after 2 attempts. Last error: {last_error}")

    except Exception as e:
        output_dict = {
            "agent_failed": True,
            "privacy_risk_level": "High",
            "cross_border_transfer_flag": True,
            "missing_safeguards": [],
            "confidence": 0.0,
            "reasoning": f"Agent failed: {str(e)}"
        }
        append_entry("agent_verdict", {
            "agent": "data_privacy",
            "clause_id": clause_id,
            "clause_text": clause_text,
            "output": output_dict
        })
        return output_dict
