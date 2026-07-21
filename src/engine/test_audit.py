import sqlite3
import os
import pytest
from src.engine.audit import append_entry, verify_chain, DB_PATH

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

def test_tamper_detection():
    # Fresh chain
    for i in range(5):
        append_entry("agent_verdict", {"clause_id": f"test-{i}", "risk_level": "low"})

    valid, broken_id = verify_chain()
    assert valid is True
    assert broken_id is None

    # Tamper directly with row 3's payload via raw SQL, bypassing the API
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Note: using seq_id to match the schema created in audit.py
    cur.execute("SELECT entry_id, payload FROM entries ORDER BY seq_id LIMIT 1 OFFSET 2")
    tampered_id, original_payload = cur.fetchone()
    cur.execute(
        "UPDATE entries SET payload = ? WHERE entry_id = ?",
        (original_payload.replace("low", "critical"), tampered_id)
    )
    conn.commit()
    conn.close()

    valid, broken_id = verify_chain()
    assert valid is False
    assert broken_id == tampered_id
