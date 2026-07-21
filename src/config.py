import os
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "local_qdrant")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

COLLECTION_COMPLIANCE = "compliance_policies"
COLLECTION_HISTORICAL = "historical_clauses"
COLLECTION_RISK = "risk_positions"
COLLECTION_REVIEW = "review_feedback"

FAULT_INJECTION = {
    "regulatory": None,
    "commercial": None,
    "precedent": None
}

def set_fault(agent_name: str, mode: str | None):
    """
    mode can be: 'crash', 'malformed', 'timeout', or None.
    """
    if agent_name in FAULT_INJECTION:
        FAULT_INJECTION[agent_name] = mode
