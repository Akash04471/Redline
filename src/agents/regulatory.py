from pydantic import BaseModel, ValidationError
import json
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_COMPLIANCE, FAULT_INJECTION
from google import genai
from google.genai import types
import os
import time
from src.engine.audit import append_entry

class RegulatoryOutput(BaseModel):
    risk_level: str  # "Low", "Medium", "High", "Critical"
    hard_flag: bool
    regulation_citation: str
    confidence: float
    reasoning: str

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
        # 1. Retrieve from Qdrant
        client = get_qdrant_client()
        query_vector = get_embedding(clause_text)
        
        # Filter by jurisdiction
        # Assuming we don't have regulation_type strictly mapped, we query by jurisdiction.
        # User requirement: "Pre-filters Qdrant 'compliance_policies' by jurisdiction + regulation_type metadata"
        # Since regulation_type isn't passed, we'll just filter by jurisdiction here.
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
        combined_context = "\n".join(citations)
        
        # 2. LLM Call definition
        instruction = (
            "You are a Senior Regulatory Compliance Officer. Analyze the provided clause "
            "against the regulatory policies. Adopt a conservative stance. Escalate via "
            "hard_flag=True on any genuine uncertainty rather than guessing low risk."
        )
        
        prompt = f"Context (Policies):\n{combined_context}\n\nClause:\n{clause_text}\n\nJurisdiction: {jurisdiction}\nContract Type: {contract_type}\n\nOutput strictly as JSON."
        
        # We try the LLM call up to 2 times to handle validation failures
        last_error = None
        for attempt in range(2):
            try:
                # Initialize GenAI client. It will use GOOGLE_API_KEY from environment or ADC.
                client = genai.Client()
                response = client.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=instruction,
                        response_mime_type="application/json",
                        response_schema=RegulatoryOutput,
                        temperature=0.1
                    )
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
                
            except ValidationError as e:
                last_error = f"Validation Error: {e}"
            except Exception as e:
                last_error = f"LLM Error: {e}"
                
        raise Exception(f"Failed after 2 attempts. Last error: {last_error}")

    except Exception as e:
        # Catch LLM fail, timeout, or Pydantic validation fail twice in a row
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
