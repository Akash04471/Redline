from src.config import set_fault, FAULT_INJECTION
from src.engine.consensus import evaluate_consensus
from src.agents.regulatory import regulatory_agent
from src.agents.commercial import commercial_risk_agent
from src.agents.precedent import precedent_agent

def reset_faults():
    for agent in FAULT_INJECTION.keys():
        set_fault(agent, None)

def test_fault_matrix():
    agents = ["regulatory", "commercial", "precedent"]
    modes = ["crash", "malformed", "timeout"]
    
    print(f"{'Agent':<15} | {'Fault Mode':<12} | {'Consensus Routing':<20} | {'Escalation Tier'}")
    print("-" * 70)
    
    clause_text = "Standard fault injection test clause."
    
    for agent_name in agents:
        for mode in modes:
            reset_faults()
            set_fault(agent_name, mode)
            
            # Construct mock clean outputs for all, then replace the faulting one with a real run
            reg_out = {"risk_level": "Low", "hard_flag": False, "confidence": 0.9}
            com_out = {"risk_level": "Low", "confidence": 0.9}
            prec_out = {"risk_level": "Low", "confidence": 0.9}
            
            if agent_name == "regulatory":
                reg_out = regulatory_agent(clause_text, "EU", "DPA")
            elif agent_name == "commercial":
                com_out = commercial_risk_agent(clause_text, "Liability", "Tech")
            elif agent_name == "precedent":
                prec_out = precedent_agent(clause_text, "Liability")
                
            decision = evaluate_consensus(
                regulatory=reg_out,
                commercial=com_out,
                precedent=prec_out,
                clause_id="fault-test-101"
            )
            
            # Verify the consensus engine correctly escalated
            assert decision.routing_decision == "human_escalate", f"Failed to escalate for {agent_name} under {mode}"
            assert decision.escalation_tier == "agent_failure", f"Incorrect tier for {agent_name} under {mode}"
            
            print(f"{agent_name:<15} | {mode:<12} | {decision.routing_decision:<20} | {decision.escalation_tier}")

if __name__ == "__main__":
    test_fault_matrix()
    print("-" * 70)
    print("All 9 fault combinations successfully degraded to 'human_escalate'.")
