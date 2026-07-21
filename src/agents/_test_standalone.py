import sys
import os

# Add root to python path so src imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.agents.regulatory import regulatory_agent
from src.agents.commercial import commercial_risk_agent
from src.agents.precedent import precedent_agent

# A clearly non-compliant GDPR data-retention clause
test_clause = "The company shall retain all customer personal data indefinitely for future marketing purposes, without requiring any opt-in."

print("=== Testing Regulatory Agent ===")
res1 = regulatory_agent(
    clause_text=test_clause,
    jurisdiction="EU",
    contract_type="Data Processing Agreement"
)
print("Regulatory Output:", res1)

print("\n=== Testing Commercial Risk Agent ===")
res2 = commercial_risk_agent(
    clause_text=test_clause,
    clause_type="Data Processing",
    industry="Technology"
)
print("Commercial Risk Output:", res2)

print("\n=== Testing Precedent Agent ===")
res3 = precedent_agent(
    clause_text=test_clause,
    clause_category="Data Processing"
)
print("Precedent Output:", res3)

