from pydantic import BaseModel
import json
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_COMPLIANCE, FAULT_INJECTION
import time
from src.engine.audit import append_entry
import logging

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

class RegulatoryOutput(BaseModel):
    risk_level: str  # "Low", "Medium", "High", "Critical"
    hard_flag: bool
    regulation_citation: str
    confidence: float
    reasoning: str

def retrieve_compliance_policies(jurisdiction: str, query: str) -> str:
    """
    Retrieve relevant regulatory compliance policies from the database for a given jurisdiction.
    
    Args:
        jurisdiction: The jurisdiction (e.g., "US", "EU").
        query: The specific clause or concept to search for.
    """
    client = get_qdrant_client()
    query_vector = get_embedding(query)
    
    jurisdiction_filter = Filter(
        must=[
            FieldCondition(
                key="jurisdiction",
                match=MatchValue(value=jurisdiction)
            )
        ]
    )
    
    search_result = client.query_points(
        collection_name=COLLECTION_COMPLIANCE,
        query=query_vector,
        query_filter=jurisdiction_filter,
        limit=3
    ).points
    
    citations = [res.payload.get("policy_text", "") for res in search_result]
    return "\\n".join(citations)

def regulatory_agent(clause_text: str, jurisdiction: str, contract_type: str, clause_id: str = "unknown") -> dict:
    """
    Agent for Regulatory Compliance.
    Role: Senior Regulatory Compliance Officer
    """
    try:
        # FAULT INJECTION GATEWAY
        fault_mode = FAULT_INJECTION.get("regulatory")
        if fault_mode == "crash":
            raise RuntimeError("Simulated agent crash.")
        elif fault_mode == "timeout":
            time.sleep(1)
            raise TimeoutError("Simulated timeout.")
        elif fault_mode == "malformed":
            raise ValueError("Simulated malformed JSON output.")
            
        # 1. Define Agent using ADK
        agent = LlmAgent(
            name="regulatory_agent",
            model="gemini-2.5-flash",
            instruction=(
                "You are a Senior Regulatory Compliance Officer. Analyze the provided clause "
                "against the regulatory policies. Adopt a conservative stance. Escalate via "
                "hard_flag=True on any genuine uncertainty rather than guessing low risk. "
                "You must output strictly as JSON matching the RegulatoryOutput schema."
            ),
            tools=[retrieve_compliance_policies],
            output_schema=RegulatoryOutput.model_json_schema()
        )
        
        # 2. Setup Session and Runner locally
        session_service = InMemorySessionService()
        runner = Runner(agent=agent, session_service=session_service, app_name="redline_engine")
        
        # We try the ADK runner up to 2 times to handle failures
        last_error = None
        for attempt in range(2):
            try:
                # 3. Execute ADK Call
                prompt = (
                    f"Clause to analyze:\\n{clause_text}\\n\\n"
                    f"Jurisdiction: {jurisdiction}\\n"
                    f"Contract Type: {contract_type}\\n\\n"
                    "Please use your tools to retrieve the compliance policies for this jurisdiction and clause, "
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
                
                # Validate using Pydantic
                validated_output = RegulatoryOutput(**parsed_json)
                output_dict = validated_output.model_dump()
                
                # Append to audit log
                append_entry("agent_verdict", {
                    "agent": "regulatory",
                    "clause_id": clause_id,
                    "clause_text": clause_text,
                    "jurisdiction": jurisdiction,
                    "contract_type": contract_type,
                    "output": output_dict
                })
                
                return output_dict
                
            except Exception as e:
                last_error = f"ADK Error: {e}"
                
        raise Exception(f"Failed after 2 attempts. Last error: {last_error}")

    except Exception as e:
        # Catch fail, timeout, or validation fail twice in a row
        # and return sentinel failure object.
        output_dict = {
            "agent_failed": True,
            "risk_level": "High",
            "hard_flag": True,
            "reasoning": f"Agent failed: {str(e)}",
            "confidence": 0.0,
            "regulation_citation": ""
        }
        append_entry("agent_verdict", {
            "agent": "regulatory",
            "clause_id": clause_id,
            "clause_text": clause_text,
            "jurisdiction": jurisdiction,
            "contract_type": contract_type,
            "output": output_dict
        })
        return output_dict
