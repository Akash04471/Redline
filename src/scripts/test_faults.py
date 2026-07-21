import json
from unittest.mock import patch, MagicMock

# Set a dummy API key so the initialization doesn't immediately fail if it checks early
import os
os.environ["GOOGLE_API_KEY"] = "DUMMY_KEY"

from src.config import set_fault, FAULT_INJECTION
from src.agents.regulatory import regulatory_agent
from src.agents.commercial import commercial_risk_agent
from src.agents.precedent import precedent_agent
from src.engine.consensus import evaluate_consensus

# A mega-JSON that satisfies all three pydantic models when parsed
mock_json_response = json.dumps({
    "risk_level": "Low",
    "hard_flag": False,
    "financial_exposure_estimate": "Low",
    "confidence": 0.95,
    "reasoning": "Looks good.",
    "similarity_score": 0.95,
    "is_standard": True,
    "deviation_notes": "None",
    "regulation_citation": "N/A"
})

def run_matrix():
    agents = ["regulatory", "commercial", "precedent"]
    modes = ["crash", "malformed", "timeout"]
    
    results_matrix = {}
    
    # We patch genai.Client so that non-faulted agents succeed cleanly
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = MagicMock(text=mock_json_response)
    
    with patch("src.agents.regulatory.genai.Client", return_value=mock_client_instance), \
         patch("src.agents.commercial.genai.Client", return_value=mock_client_instance), \
         patch("src.agents.precedent.genai.Client", return_value=mock_client_instance):
         
        for agent in agents:
            results_matrix[agent] = {}
            for mode in modes:
                # 1. Set the fault
                set_fault(agent, mode)
                
                # 2. Run all three agents
                # We use dummy inputs. The mock Qdrant client might fail if Qdrant isn't running?
                # Actually Qdrant is running locally, we can just pass dummy texts.
                
                reg_out = regulatory_agent("dummy clause", "EU", "DPA", "c1")
                com_out = commercial_risk_agent("dummy clause", "Data Processing", "Tech", "c1")
                prec_out = precedent_agent("dummy clause", "Data Processing", "c1")
                
                # 3. Consensus Engine
                cons = evaluate_consensus(reg_out, com_out, prec_out, "c1")
                
                # Record result
                results_matrix[agent][mode] = cons.routing_decision
                
                # Clean up
                set_fault(agent, None)
                
    # Print the matrix beautifully
    print(f"{'Agent / Fault Mode':<20} | {'crash':<15} | {'malformed':<15} | {'timeout':<15}")
    print("-" * 72)
    for agent in agents:
        crash_res = results_matrix[agent]["crash"]
        mal_res = results_matrix[agent]["malformed"]
        time_res = results_matrix[agent]["timeout"]
        print(f"{agent:<20} | {crash_res:<15} | {mal_res:<15} | {time_res:<15}")

if __name__ == "__main__":
    run_matrix()
