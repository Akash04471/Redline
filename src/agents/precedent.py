from pydantic import BaseModel, ValidationError
import json
import time
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.config import COLLECTION_HISTORICAL, COLLECTION_REVIEW, FAULT_INJECTION
from google import genai
from google.genai import types
from src.engine.audit import append_entry

class PrecedentOutput(BaseModel):
    similarity_score: float
    is_standard: bool
    deviation_notes: str
    confidence: float
    reasoning: str

def precedent_agent(clause_text: str, clause_category: str, clause_id: str = "unknown") -> dict:
    """
    Agent for Precedent.
    Role: Senior Paralegal / Knowledge Manager
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

        client = get_qdrant_client()
        query_vector = get_embedding(clause_text)
        
        historical_filter = Filter(must=[FieldCondition(key="clause_category", match=MatchValue(value=clause_category))])
        
        hist_results = client.query_points(
            collection_name=COLLECTION_HISTORICAL,
            query=query_vector,
            query_filter=historical_filter,
            limit=5
        ).points
        
        review_results = client.query_points(
            collection_name=COLLECTION_REVIEW,
            query=query_vector,
            # If review_feedback has no clause_category, we might skip the filter or use a generic one.
            # Assuming review_feedback might not have clause_category (as per setup_db.py schema)
            # We'll just search it without filter for top matches.
            limit=5
        ).points
        
        # Combine and sort by score
        combined_results = hist_results + review_results
        combined_results.sort(key=lambda x: x.score, reverse=True)
        top_5 = combined_results[:5]
        
        citations = []
        for res in top_5:
            # Check if it's historical or review
            if "outcome" in res.payload:
                citations.append(f"Historical Clause ({res.payload.get('outcome')}): {res.payload.get('clause_text')}")
            else:
                citations.append(f"Review Feedback ({res.payload.get('decision')} - {res.payload.get('rationale')}): {res.payload.get('clause_text')}")
                
        combined_context = "\n".join(citations)

        instruction = "You are a Senior Paralegal / Knowledge Manager evaluating precedents."
        prompt = f"Context (Precedents):\n{combined_context}\n\nClause:\n{clause_text}\n\nClause Category: {clause_category}\n\nOutput strictly as JSON."
        
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
                        response_schema=PrecedentOutput,
                        temperature=0.1
                    )
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
                
            except ValidationError as e:
                last_error = f"Validation Error: {e}"
            except Exception as e:
                last_error = f"LLM Error: {e}"
                
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
