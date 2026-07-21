import uuid
from src.db.client import client, create_collections
from src.db.embeddings import get_embedding
from qdrant_client.models import PointStruct

COMPLIANCE_POLICIES = [
    {"jurisdiction": "EU", "regulation_type": "GDPR", "effective_date": "2018-05-25", "policy_text": "All data subjects have the right to request deletion of their personal data within 30 days of notice."},
    {"jurisdiction": "US/CA", "regulation_type": "CCPA", "effective_date": "2020-01-01", "policy_text": "Covered businesses must provide a clear 'Do Not Sell My Personal Information' link on their homepage."},
    {"jurisdiction": "US", "regulation_type": "GLBA", "effective_date": "2001-07-01", "policy_text": "Financial institutions must maintain comprehensive written information security programs."},
    {"jurisdiction": "EU", "regulation_type": "AI Act", "effective_date": "2024-05-01", "policy_text": "High-risk AI systems must undergo conformity assessments before being deployed in the EU market."},
    {"jurisdiction": "US/NY", "regulation_type": "NY SHIELD", "effective_date": "2020-03-21", "policy_text": "Any person or business owning or licensing computerized data which includes private information of a resident of New York must implement and maintain reasonable safeguards."},
    # Add more to reach ~20...
    *[{"jurisdiction": "Generic", "regulation_type": "Standard Data Protection", "effective_date": "2023-01-01", "policy_text": f"Standard internal data processing guideline rule {i}: Access logs must be retained for at least 90 days."} for i in range(15)]
]

HISTORICAL_CLAUSES = [
    {"contract_type": "SaaS Agreement", "clause_category": "Indemnification", "outcome": "Accepted", "timestamp": "2023-01-15T10:00:00Z", "clause_text": "Provider shall indemnify and hold harmless Customer against any third-party claims arising from Provider's breach of confidentiality."},
    {"contract_type": "MSA", "clause_category": "Liability Cap", "outcome": "Negotiated - Cap Raised", "timestamp": "2023-04-10T14:30:00Z", "clause_text": "In no event shall either party's aggregate liability exceed the total amounts paid under this Agreement in the twelve months preceding the claim."},
    {"contract_type": "Vendor Agreement", "clause_category": "Force Majeure", "outcome": "Accepted", "timestamp": "2022-09-01T09:15:00Z", "clause_text": "Neither party shall be liable for delays caused by acts of God, pandemics, or government mandates."},
    {"contract_type": "DPA", "clause_category": "Data Processing", "outcome": "Accepted", "timestamp": "2023-11-20T11:00:00Z", "clause_text": "Data Processor shall only process Personal Data in accordance with the documented instructions of the Data Controller."},
    {"contract_type": "NDA", "clause_category": "Termination", "outcome": "Rejected", "timestamp": "2024-01-05T16:45:00Z", "clause_text": "Either party may terminate this agreement at any time for convenience with 5 days written notice."},
    # Borderline clause that is compliant under old policies (GDPR 30 days) but will fail a stricter one (e.g. 15 days or 7 days)
    {"contract_type": "DPA", "jurisdiction": "EU", "clause_category": "Data Deletion", "outcome": "Accepted", "timestamp": "2023-06-15T10:00:00Z", "clause_text": "Upon request, provider will delete personal data within 30 days of notice."},
    # Add more to reach ~20...
    *[{"contract_type": "Generic Agreement", "clause_category": "General", "outcome": "Accepted", "timestamp": "2024-02-01T10:00:00Z", "clause_text": f"Standard boiler plate clause {i}: This agreement is governed by the laws of the applicable jurisdiction without regard to conflict of law principles."} for i in range(14)]
]

RISK_POSITIONS = [
    {"clause_type": "Indemnification", "industry": "Healthcare", "risk_tolerance_notes": "Low tolerance. Require broad indemnification for HIPAA breaches. Will not accept caps on data breach liability."},
    {"clause_type": "Data Processing", "industry": "Technology", "risk_tolerance_notes": "Medium tolerance. Standard SCCs required for EU data transfers. Sub-processors must be pre-approved."},
    {"clause_type": "Termination for Convenience", "industry": "Finance", "risk_tolerance_notes": "Zero tolerance. Vendor cannot terminate for convenience; requires minimum 180-day transition period."},
    {"clause_type": "IP Assignment", "industry": "Software", "risk_tolerance_notes": "Low tolerance. All IP developed during the engagement must be assigned immediately to the Company."},
    {"clause_type": "Liability Cap", "industry": "Retail", "risk_tolerance_notes": "High tolerance for standard software, but cap must be at least 2x annual contract value for mission-critical systems."},
    # Add more to reach ~20...
    *[{"clause_type": "Miscellaneous", "industry": "General", "risk_tolerance_notes": f"Standard risk position {i}: Avoid unlimited liability unless related to gross negligence."} for i in range(15)]
]

REVIEW_FEEDBACK = [
    {"decision": "Rejected", "rationale": "The limitation of liability excludes gross negligence, which violates our standard risk policy for vendors handling PII.", "reviewer_id": "reviewer_12", "timestamp": "2024-01-20T09:00:00Z", "clause_text": "Liability is capped at the contract value, excluding any claims related to gross negligence."},
    {"decision": "Approved with Changes", "rationale": "Added reciprocal confidentiality obligations to balance the one-sided draft provided by the counterparty.", "reviewer_id": "reviewer_05", "timestamp": "2024-02-15T14:20:00Z", "clause_text": "Both parties agree to hold all Confidential Information in strict confidence and not to disclose it to any third party."},
    {"decision": "Approved", "rationale": "Standard force majeure clause aligned with industry norms.", "reviewer_id": "reviewer_02", "timestamp": "2023-10-10T11:45:00Z", "clause_text": "Neither party is liable for delays due to circumstances beyond their reasonable control."},
    # Add more to reach ~20...
    *[{"decision": "Approved", "rationale": "Looks standard.", "reviewer_id": f"reviewer_{i}", "timestamp": "2024-03-01T10:00:00Z", "clause_text": f"General provision {i} text evaluated and found acceptable based on current playbook."} for i in range(17)]
]


def seed_collection(collection_name: str, data: list, text_key: str):
    points = []
    for item in data:
        text = item[text_key]
        vector = get_embedding(text)
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=item
            )
        )
    
    if points:
        client.upsert(
            collection_name=collection_name,
            points=points
        )
    print(f"Collection '{collection_name}' seeded with {len(points)} records.")


def main():
    print("Creating collections...")
    create_collections()
    
    print("Seeding 'compliance_policies'...")
    seed_collection("compliance_policies", COMPLIANCE_POLICIES, "policy_text")
    
    print("Seeding 'historical_clauses'...")
    seed_collection("historical_clauses", HISTORICAL_CLAUSES, "clause_text")
    
    print("Seeding 'risk_positions'...")
    seed_collection("risk_positions", RISK_POSITIONS, "risk_tolerance_notes")
    
    print("Seeding 'review_feedback'...")
    seed_collection("review_feedback", REVIEW_FEEDBACK, "clause_text")
    
    print("Database setup complete.")

if __name__ == "__main__":
    main()
