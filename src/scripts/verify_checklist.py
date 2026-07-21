import os
import json
import sqlite3
from unittest.mock import patch, MagicMock

# Set dummy API key
os.environ["GOOGLE_API_KEY"] = "DUMMY_KEY"

from src.scripts.compliance_sweep import run_sweep
from src.engine.audit import verify_chain, append_entry, get_chain_for_clause
from src.db.client import get_qdrant_client
from src.config import COLLECTION_COMPLIANCE

print("--- Tab 1 Verifications ---")
# Graceful Qdrant fail is handled by try/except in app.py

print("\n--- Tab 3 Verifications (Sweep Duplication) ---")
policy = "Duplicate Policy Test 123"
# Run 1
with patch("src.scripts.compliance_sweep.regulatory_agent", return_value={"risk_level":"Low"}):
    res1 = run_sweep(policy, "US", "TEST")
# Run 2
with patch("src.scripts.compliance_sweep.regulatory_agent", return_value={"risk_level":"Low"}):
    res2 = run_sweep(policy, "US", "TEST")

client = get_qdrant_client()
points, _ = client.scroll(collection_name=COLLECTION_COMPLIANCE, limit=100, with_payload=True, with_vectors=False)
dupes = [p for p in points if p.payload and p.payload.get("policy_text") == policy]
print(f"Number of instances of policy in Qdrant: {len(dupes)}")
assert len(dupes) == 1, "Duplicate policy inserted!"

print("\n--- Tab 4 Verifications (Tamper Test) ---")
# Insert a legit entry
append_entry("test_tamper", {"foo": "bar"})
v1, _ = verify_chain()
print(f"Chain before tamper is valid: {v1}")

# Tamper
conn = sqlite3.connect("audit.db")
c = conn.cursor()
c.execute("SELECT seq_id, payload FROM entries ORDER BY seq_id DESC LIMIT 1")
seq_id, payload_str = c.fetchone()
payload = json.loads(payload_str)
payload["foo"] = "tampered"
c.execute("UPDATE entries SET payload = ? WHERE seq_id = ?", (json.dumps(payload), seq_id))
conn.commit()
conn.close()

v2, broken_id = verify_chain()
print(f"Chain after tamper is valid: {v2} (Broken at entry: {broken_id})")
