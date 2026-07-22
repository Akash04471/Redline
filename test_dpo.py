import asyncio
from src.engine.workflow import run_workflow
import json

clause_data = {
    "clause_id": "test-dpo-123",
    "clause_text": "The Provider agrees to process personal data strictly in accordance with documented instructions. Upon request, the Provider must delete personal data within 30 days of notice.",
    "jurisdiction": "EU",
    "contract_type": "DPA",
    "clause_category": "Data Processing",
    "clause_type": "Data Processing",
    "industry": "Technology"
}

res = run_workflow(clause_data)
print(json.dumps(res.raw_outputs, indent=2))
print("Consensus Decision:", res.consensus_decision.model_dump())
