from pydantic import BaseModel
from typing import Literal
from src.engine.audit import append_entry

class ConsensusOutput(BaseModel):
    consensus: bool
    escalation_tier: Literal["none", "advisory", "material_conflict", "compliance_hard_flag", "agent_failure"]
    routing_decision: Literal["auto_recommend", "human_escalate"]
    summary: str

SEVERITY = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3
}

def evaluate_consensus(regulatory: dict, commercial: dict, precedent: dict, clause_id: str = "unknown") -> ConsensusOutput:
    """
    Evaluates the outputs from three specialist agents and determines the consensus and escalation routing.
    """
    result = None
    # 1. Agent Failure Check
    if regulatory.get("agent_failed") or commercial.get("agent_failed") or precedent.get("agent_failed"):
        result = ConsensusOutput(
            consensus=False,
            escalation_tier="agent_failure",
            routing_decision="human_escalate",
            summary="One or more agents failed to produce a valid response. Escalating for manual review."
        )
    
    if result is None:
        # 2. Compliance Hard Flag Check
        if regulatory.get("hard_flag"):
            result = ConsensusOutput(
                consensus=False,
                escalation_tier="compliance_hard_flag",
                routing_decision="human_escalate",
                summary="Regulatory agent flagged a hard compliance risk."
            )
        
    # Extract Risk Levels
    # For precedent, if risk_level is missing, assume it maps from is_standard
    if "risk_level" in precedent:
        prec_risk = precedent["risk_level"].lower()
    else:
        prec_risk = "low" if precedent.get("is_standard") else "high"
        
    reg_risk = regulatory.get("risk_level", "").lower()
    com_risk = commercial.get("risk_level", "").lower()
    
    # Map to severity scores (if unknown, assign 99 to fail the match)
    reg_sev = SEVERITY.get(reg_risk, 99)
    com_sev = SEVERITY.get(com_risk, 99)
    prec_sev = SEVERITY.get(prec_risk, 99)
    
    sevs = [reg_sev, com_sev, prec_sev]
    
    # Extract Confidence Scores
    reg_conf = regulatory.get("confidence", 0.0)
    com_conf = commercial.get("confidence", 0.0)
    prec_conf = precedent.get("confidence", 0.0)
    
    confs = [reg_conf, com_conf, prec_conf]
    
    if result is None:
        # 3. Full Consensus Check
        if reg_sev == com_sev == prec_sev and min(confs) >= 0.75:
            result = ConsensusOutput(
                consensus=True,
                escalation_tier="none",
                routing_decision="auto_recommend",
                summary=f"All agents agree this is {reg_risk.capitalize()} risk with high confidence."
            )
        
    # 4. Advisory Check (max 1 severity step difference, max 0.15 confidence gap)
    max_sev = max(sevs)
    min_sev = min(sevs)
    sev_gap = max_sev - min_sev
    
    max_conf = max(confs)
    min_conf = min(confs)
    conf_gap = max_conf - min_conf
    
    if result is None:
        if sev_gap <= 1 and conf_gap <= 0.15:
            result = ConsensusOutput(
                consensus=False,
                escalation_tier="advisory",
                routing_decision="human_escalate",
                summary=f"Agents slightly disagree on risk level (max 1 step) with similar confidence scores, requiring a quick advisory review."
            )
            
    if result is None:
        # 5. Material Conflict (everything else)
        result = ConsensusOutput(
            consensus=False,
            escalation_tier="material_conflict",
            routing_decision="human_escalate",
            summary=f"Regulatory assessed {reg_risk} risk ({reg_conf*100:.0f}% conf), Commercial assessed {com_risk} risk ({com_conf*100:.0f}% conf), and Precedent assessed {prec_risk} risk ({prec_conf*100:.0f}% conf). Escalated as a material conflict."
        )

    append_entry("consensus_decision", {
        "clause_id": clause_id,
        "inputs": {
            "regulatory": regulatory,
            "commercial": commercial,
            "precedent": precedent
        },
        "output": result.model_dump()
    })
    return result
