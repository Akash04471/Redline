from pydantic import BaseModel, ValidationError
import json
import time
import os
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_RISK, FAULT_INJECTION
from google import genai
from google.genai import types
from src.engine.audit import append_entry

class CommercialOutput(BaseModel):
    risk_level: str
    financial_exposure_estimate: str
    confidence: float
    reasoning: str

def commercial_risk_agent(clause_text: str, clause_type: str, industry: str, clause_id: str = "unknown") -> dict:
    """
    Agent for Commercial Risk.
    Role: Corporate Risk Manager
    """
    try:
        # FAULT INJECTION GATEWAY
        fault_mode = FAULT_INJECTION.get("commercial")
        if fault_mode == "crash":
            raise RuntimeError("Simulated agent crash.")
        elif fault_mode == "timeout":
            time.sleep(1)
            raise TimeoutError("Simulated timeout.")
        elif fault_mode == "malformed":
            raise ValueError("Simulated malformed JSON output.")

        client = get_qdrant_client()
        query_vector = get_embedding(clause_text)
        
        # Metadata filter on clause_type + industry
        risk_filter = Filter(
            must=[
                FieldCondition(key="clause_type", match=MatchValue(value=clause_type)),
                FieldCondition(key="industry", match=MatchValue(value=industry))
            ]
        )
        
        search_result = client.query_points(
            collection_name=COLLECTION_RISK,
            query=query_vector,
            query_filter=risk_filter,
            limit=2
        ).points
        
        citations = [res.payload.get("risk_tolerance_notes", "") for res in search_result]
        combined_context = "\n".join(citations)

        instruction = "You are a Corporate Risk Manager evaluating contractual clauses against risk positions."
        prompt = f"Context (Risk Positions):\n{combined_context}\n\nClause:\n{clause_text}\n\nClause Type: {clause_type}\nIndustry: {industry}\n\nOutput strictly as JSON."
        
        last_error = None
        for attempt in range(2):
            try:
                genai_client = genai.Client()
                response = genai_client.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=instruction,
                        response_mime_type="application/json",
                        response_schema=CommercialOutput,
                        temperature=0.1
                    )
                )
                
                output_text = response.text
                if not output_text:
                    raise ValueError("Empty response from LLM")
                    
                parsed_json = json.loads(output_text)
                validated_output = CommercialOutput(**parsed_json)
                output_dict = validated_output.model_dump()
                
                # Append to audit log
                append_entry("agent_verdict", {
                    "agent": "commercial",
                    "clause_id": clause_id,
                    "clause_text": clause_text,
                    "clause_type": clause_type,
                    "industry": industry,
                    "output": output_dict
                })
                
                return output_dict
                
            except ValidationError as e:
                last_error = f"Validation Error: {e}"
            except Exception as e:
                last_error = f"LLM Error: {e}"
                
        raise Exception(f"Failed after 2 attempts. Last error: {last_error}")

    except Exception as e:
        output_dict = {
            "agent_failed": True,
            "risk_level": "High",
            "financial_exposure_estimate": "Unknown",
            "confidence": 0.0,
            "reasoning": f"Agent failed: {str(e)}"
        }
        append_entry("agent_verdict", {
            "agent": "commercial",
            "clause_id": clause_id,
            "clause_text": clause_text,
            "clause_type": clause_type,
            "industry": industry,
            "output": output_dict
        })
        return output_dict
