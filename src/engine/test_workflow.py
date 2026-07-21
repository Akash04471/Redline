import os
import sqlite3
from unittest.mock import patch
import json
from src.engine.workflow import run_workflow
from src.engine.audit import get_chain_for_clause, DB_PATH, append_entry

def _mock_agents_for_scenario(scenario_name: str, clause_id: str, clause_text: str):
    """
    Returns mock functions for the 3 agents based on the desired scenario to 
    bypass LLM keys and deterministically trigger exact routing paths.
    """
    def mock_reg(*args, **kwargs):
        if scenario_name == "clean_consensus":
            res = {"risk_level": "Low", "confidence": 0.9, "hard_flag": False, "reasoning": "Standard."}
        elif scenario_name == "material_conflict":
            res = {"risk_level": "Low", "confidence": 0.9, "hard_flag": False, "reasoning": "Looks fine."}
        elif scenario_name == "hard_flag":
            res = {"risk_level": "High", "confidence": 0.9, "hard_flag": True, "reasoning": "Violates GDPR."}
        append_entry("agent_verdict", {"agent": "regulatory", "clause_id": clause_id, "output": res})
        return res
            
    def mock_com(*args, **kwargs):
        if scenario_name == "clean_consensus":
            res = {"risk_level": "Low", "confidence": 0.9, "reasoning": "Standard."}
        elif scenario_name == "material_conflict":
            res = {"risk_level": "High", "confidence": 0.9, "reasoning": "Huge financial risk."}
        elif scenario_name == "hard_flag":
            res = {"risk_level": "Low", "confidence": 0.9, "reasoning": "Standard."}
        append_entry("agent_verdict", {"agent": "commercial", "clause_id": clause_id, "output": res})
        return res

    def mock_prec(*args, **kwargs):
        if scenario_name == "clean_consensus":
            res = {"risk_level": "Low", "confidence": 0.9, "is_standard": True, "reasoning": "Standard."}
        elif scenario_name == "material_conflict":
            res = {"risk_level": "Low", "confidence": 0.9, "is_standard": True, "reasoning": "Standard."}
        elif scenario_name == "hard_flag":
            res = {"risk_level": "Low", "confidence": 0.9, "is_standard": True, "reasoning": "Standard."}
        append_entry("agent_verdict", {"agent": "precedent", "clause_id": clause_id, "output": res})
        return res

    return mock_reg, mock_com, mock_prec

def test_scenario(scenario_id: str, clause_id: str):
    # Base clause data
    clause_data = {
        "clause_id": clause_id,
        "clause_text": "Sample clause text",
        "jurisdiction": "EU",
        "contract_type": "DPA",
        "clause_type": "Liability",
        "industry": "Tech",
        "clause_category": "Limitation of Liability"
    }

    # Patch the agents directly in the workflow module where they are imported
    reg_mock, com_mock, prec_mock = _mock_agents_for_scenario(scenario_id, clause_id, clause_data["clause_text"])
    
    def mock_rec(*args, **kwargs):
        res = {
            "suggested_redline_text": "Revised text.",
            "plain_language_rationale": "Made it better.",
            "confidence_score": 0.9,
            "cited_sources": []
        }
        append_entry("agent_verdict", {"agent": "recommendation", "clause_id": clause_id, "output": res})
        return res
    
    print(f"\n{'='*50}\nRunning Scenario: {scenario_id}\n{'='*50}")
    
    with patch('src.engine.workflow.regulatory_agent', side_effect=reg_mock), \
         patch('src.engine.workflow.commercial_risk_agent', side_effect=com_mock), \
         patch('src.engine.workflow.precedent_agent', side_effect=prec_mock), \
         patch('src.engine.workflow.recommendation_agent', side_effect=mock_rec):
         
         result = run_workflow(clause_data)
         
    print(f"\nWORKFLOW RESULT:")
    print(f"Consensus Decision: {result.consensus_decision['consensus']}")
    print(f"Escalation Tier: {result.consensus_decision['escalation_tier']}")
    
    # We now receive a Dict from branch_outcome instead of a string
    if result.consensus_decision['consensus'] is True:
        print(f"Branch Triggered: Recommendation Agent")
        print(f"Redline: {result.branch_outcome.get('suggested_redline_text')}")
    else:
        print(f"Branch Triggered: Human Review Agent")
        # Manually call capture_human_decision
        from src.agents.human_review import capture_human_decision
        
        print("\n=> Simulating Human Decision...")
        capture_human_decision(
            clause_id=clause_id,
            clause_text=clause_data["clause_text"],
            decision="Accepted with custom edits",
            final_text="This is the final human-edited redline.",
            rationale="Needed to mitigate the severe financial risk.",
            reviewer_id="human_reviewer_99"
        )
        
        # Confirm Qdrant point exists
        from src.db.client import get_qdrant_client
        client = get_qdrant_client()
        points, _ = client.scroll(
            collection_name="review_feedback",
            with_payload=True,
            limit=100
        )
        
        print("\n=> Qdrant `review_feedback` Collection Points:")
        found = False
        for p in points:
            if p.payload.get("clause_id") == clause_id:
                print(f"   [FOUND] ID: {p.id} | Decision: {p.payload.get('decision')} | Reviewer: {p.payload.get('reviewer_id')}")
                found = True
        if not found:
            print("   [ERROR] Point not found in Qdrant!")

    print(f"\nAUDIT CHAIN FOR {clause_id}:")
    chain = get_chain_for_clause(clause_id)
    for entry in chain:
        print(f" - [{entry.entry_type}] seq_id: {entry.seq_id} | prev: {entry.prev_hash[:8]}... | hash: {entry.payload_hash[:8]}...")
        if entry.entry_type == "consensus_decision":
            print(f"   => Decision logged: {entry.payload['output']['escalation_tier']}")
        if entry.entry_type == "human_decision":
            print(f"   => Human Decision logged: {entry.payload['decision']}")

def run_all_tests():
    # Clean DBs
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    from src.db.client import create_collections, get_qdrant_client
    # Make sure collections exist
    create_collections()
    client = get_qdrant_client()
    # Actually qdrant-client might require a filter, let's just recreate it
    client.delete_collection("review_feedback")
    create_collections()
        
    test_scenario("clean_consensus", "clause_clean_101")
    test_scenario("material_conflict", "clause_conflict_202")
    test_scenario("hard_flag", "clause_hardflag_303")

if __name__ == "__main__":
    run_all_tests()
