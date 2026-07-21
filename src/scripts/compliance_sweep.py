import uuid
from typing import List, Dict, Any
from pydantic import BaseModel
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from src.db.client import get_qdrant_client
from src.db.embeddings import get_embedding
from src.agents.regulatory import regulatory_agent
from src.engine.audit import append_entry
from src.config import COLLECTION_COMPLIANCE, COLLECTION_HISTORICAL

class FlaggedClause(BaseModel):
    clause_id: str
    clause_text: str
    risk_level: str
    hard_flag: bool
    violation_reason: str
    citation: str

class SweepResult(BaseModel):
    total_scanned: int
    total_flagged: int
    flagged_clauses: List[FlaggedClause]

def run_sweep(new_policy_text: str, jurisdiction: str, regulation_type: str) -> SweepResult:
    """
    Executes a compliance sweep to test historical clauses against a newly introduced policy.
    """
    client = get_qdrant_client()
    
    # 1. Upsert new policy
    policy_vector = get_embedding(new_policy_text)
    
    import hashlib
    policy_id = hashlib.sha256(new_policy_text.encode('utf-8')).hexdigest()
    # UUIDs require a specific format for Qdrant depending on settings, but string UUID is standard. 
    # Let's format it as a valid UUID string from the hash.
    policy_id = str(uuid.UUID(policy_id[:32]))
    
    client.upsert(
        collection_name=COLLECTION_COMPLIANCE,
        points=[
            PointStruct(
                id=policy_id,
                vector=policy_vector,
                payload={
                    "jurisdiction": jurisdiction,
                    "regulation_type": regulation_type,
                    "policy_text": new_policy_text
                }
            )
        ]
    )
    
    print(f"Upserted new policy ({jurisdiction}/{regulation_type}) with ID: {policy_id}")
    
    # 2. Semantically query historical_clauses
    # We use a score threshold of 0.65 to capture relevant clauses without returning everything.
    search_result = client.query_points(
        collection_name=COLLECTION_HISTORICAL,
        query=policy_vector,
        limit=50,
        score_threshold=0.65,
        # A real system might also filter historical clauses by jurisdiction if that field exists on them,
        # but the prompt says to find related clauses using semantic similarity.
    )
    
    scanned_count = len(search_result.points)
    flagged = []
    
    print(f"Found {scanned_count} historically relevant clauses for this policy.")
    
    # 3. For each matched historical clause, re-run Regulatory Compliance Agent
    for hit in search_result.points:
        clause_id = str(hit.id)
        clause_text = hit.payload.get("clause_text", "")
        # Assuming contract_type is available, otherwise use a default
        contract_type = hit.payload.get("contract_type", "Unknown")
        
        # We pass the jurisdiction of the new policy so the agent pulls the correct laws
        reg_output = regulatory_agent(clause_text, jurisdiction, contract_type, clause_id)
        
        # 4. Check if newly non-compliant
        # Depending on whether we get a Pydantic object or a dict (since standalone mock returns dict)
        if isinstance(reg_output, dict):
            is_high_risk = reg_output.get("risk_level") in ["High", "Critical"]
            is_hard_flag = reg_output.get("hard_flag") is True
            reason = reg_output.get("reasoning", "")
            cit = reg_output.get("regulation_citation", "")
            risk_val = reg_output.get("risk_level", "Unknown")
        else:
            is_high_risk = reg_output.risk_level in ["High", "Critical"]
            is_hard_flag = reg_output.hard_flag is True
            reason = reg_output.reasoning
            cit = reg_output.regulation_citation
            risk_val = reg_output.risk_level
            
        if is_high_risk or is_hard_flag:
            flagged.append(FlaggedClause(
                clause_id=clause_id,
                clause_text=clause_text,
                risk_level=risk_val,
                hard_flag=is_hard_flag,
                violation_reason=reason,
                citation=cit
            ))
            
    # 5. Log the sweep to the audit ledger
    result = SweepResult(
        total_scanned=scanned_count,
        total_flagged=len(flagged),
        flagged_clauses=flagged
    )
    
    append_entry("compliance_sweep", {
        "policy_applied": {
            "policy_id": policy_id,
            "policy_text": new_policy_text,
            "jurisdiction": jurisdiction
        },
        "total_scanned": scanned_count,
        "newly_flagged_count": len(flagged),
        "flagged_clauses": [f.model_dump() for f in flagged]
    })
    
    return result

if __name__ == "__main__":
    from unittest.mock import patch
    import json
    
    print("--- Running Sweep Test ---")
    stricter_policy = "Upon request, providers must delete personal data within 15 days of notice, no exceptions."
    
    def mock_reg(clause_text, jur, ctype, clause_id):
        # Only flag the borderline clause
        if "delete personal data within 30 days" in clause_text:
            return {
                "risk_level": "High",
                "hard_flag": True,
                "reasoning": "Fails the 15-day strict deletion requirement introduced by the new sweep.",
                "regulation_citation": "New Strict Policy",
                "confidence": 0.95
            }
        else:
            return {
                "risk_level": "Low",
                "hard_flag": False,
                "reasoning": "Acceptable under new policy.",
                "regulation_citation": "New Strict Policy",
                "confidence": 0.95
            }
            
    # Overwrite the imported function for the test
    global regulatory_agent
    regulatory_agent = mock_reg
    
    res = run_sweep(
        new_policy_text=stricter_policy,
        jurisdiction="EU",
        regulation_type="GDPR-Strict"
    )
    
    print(f"\nSweep completed. Scanned: {res.total_scanned}, Flagged: {res.total_flagged}")
    print(json.dumps([f.model_dump() for f in res.flagged_clauses], indent=2))

