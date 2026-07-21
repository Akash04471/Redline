from pydantic import BaseModel
from typing import Any, Dict
from datetime import datetime, timezone
import uuid
from src.engine.audit import append_entry
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from qdrant_client.models import PointStruct

class ReviewPackage(BaseModel):
    clause_id: str
    clause_text: str
    escalation_tier: str
    summary: str
    expert_outputs: Dict[str, Any]

def human_review_agent(clause_id: str, clause_text: str, consensus_decision: dict, raw_outputs: dict) -> dict:
    """
    Packages the outputs for a UI to present to a human reviewer.
    This is a data-shaping function, no LLM call is required.
    """
    package = ReviewPackage(
        clause_id=clause_id,
        clause_text=clause_text,
        escalation_tier=consensus_decision.get("escalation_tier", "unknown"),
        summary=consensus_decision.get("summary", "No summary provided."),
        expert_outputs=raw_outputs
    )
    return package.model_dump()

def capture_human_decision(clause_id: str, clause_text: str, decision: str, final_text: str, rationale: str, reviewer_id: str):
    """
    Called by the UI to register the human's final resolution of the clause.
    Writes to the audit log and upserts the decision into the Qdrant review_feedback collection.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    payload = {
        "clause_id": clause_id,
        "decision": decision,
        "final_text": final_text,
        "rationale": rationale,
        "reviewer_id": reviewer_id,
        "timestamp": timestamp
    }
    
    # 1. Audit Log
    append_entry("human_decision", payload)
    
    # 2. Qdrant Upsert
    client = get_qdrant_client()
    vector = get_embedding(clause_text)
    
    # Generate a unique point ID for Qdrant (UUID string)
    point_id = str(uuid.uuid4())
    
    client.upsert(
        collection_name="review_feedback",
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
        ]
    )
    
    return payload
