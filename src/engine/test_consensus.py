import pytest
from src.engine.consensus import evaluate_consensus

def test_agent_failure():
    reg = {"agent_failed": True, "risk_level": "High", "confidence": 0.0, "hard_flag": True}
    com = {"risk_level": "Low", "confidence": 0.9}
    prec = {"risk_level": "Low", "confidence": 0.8}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    assert res.escalation_tier == "agent_failure"
    assert res.routing_decision == "human_escalate"
    
def test_compliance_hard_flag():
    reg = {"risk_level": "High", "confidence": 0.9, "hard_flag": True}
    com = {"risk_level": "High", "confidence": 0.9}
    prec = {"risk_level": "High", "confidence": 0.9}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    assert res.escalation_tier == "compliance_hard_flag"
    assert res.routing_decision == "human_escalate"
    
def test_consensus_auto_recommend():
    reg = {"risk_level": "Low", "confidence": 0.8, "hard_flag": False}
    com = {"risk_level": "Low", "confidence": 0.85}
    prec = {"risk_level": "Low", "confidence": 0.9}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is True
    assert res.escalation_tier == "none"
    assert res.routing_decision == "auto_recommend"
    
def test_advisory():
    # Max 1 severity step diff (Low vs Medium)
    # Confidence gap: 0.9 - 0.8 = 0.1 <= 0.15
    reg = {"risk_level": "Medium", "confidence": 0.8, "hard_flag": False}
    com = {"risk_level": "Low", "confidence": 0.9}
    prec = {"risk_level": "Low", "confidence": 0.85}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    assert res.escalation_tier == "advisory"
    assert res.routing_decision == "human_escalate"
    
def test_material_conflict_severity():
    # >1 severity step diff (Low vs High)
    reg = {"risk_level": "High", "confidence": 0.9, "hard_flag": False}
    com = {"risk_level": "Low", "confidence": 0.9}
    prec = {"risk_level": "Low", "confidence": 0.9}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    assert res.escalation_tier == "material_conflict"
    assert res.routing_decision == "human_escalate"
    
def test_material_conflict_confidence():
    # 1 severity diff, but confidence gap is > 0.15 (0.9 vs 0.7)
    reg = {"risk_level": "Medium", "confidence": 0.7, "hard_flag": False}
    com = {"risk_level": "Low", "confidence": 0.9}
    prec = {"risk_level": "Low", "confidence": 0.85}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    assert res.escalation_tier == "material_conflict"
    assert res.routing_decision == "human_escalate"

def test_material_conflict_confidence_below_threshold_consensus():
    # All match, but confidence below 0.75 for one agent
    reg = {"risk_level": "Low", "confidence": 0.7, "hard_flag": False}
    com = {"risk_level": "Low", "confidence": 0.72}
    prec = {"risk_level": "Low", "confidence": 0.74}
    
    res = evaluate_consensus(reg, com, prec)
    assert res.consensus is False
    # Gap is 0.04 <= 0.15, severity diff is 0 <= 1
    # Thus falls into advisory! Wait, does it? 
    # Let's check branch 3 (full consensus) fails.
    # Branch 4 (advisory): gap=0.04 (<=0.15), sev=0 (<=1). So it SHOULD be advisory.
    assert res.escalation_tier == "advisory"
    assert res.routing_decision == "human_escalate"
