import sqlite3
import json
import hashlib
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

DB_PATH = "audit.db"

class AuditEntry(BaseModel):
    entry_id: str
    timestamp: str
    entry_type: str
    payload: dict
    payload_hash: str
    prev_hash: str
    seq_id: Optional[int] = None

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def _hash_payload(payload: dict) -> str:
    canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

def append_entry(entry_type: str, payload: dict, db_path: str = DB_PATH) -> AuditEntry:
    init_db(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get last prev_hash
    cursor.execute("SELECT payload_hash FROM entries ORDER BY seq_id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_hash = row[0] if row else "GENESIS"
    
    entry_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_hash = _hash_payload(payload)
    
    cursor.execute('''
        INSERT INTO entries (entry_id, timestamp, entry_type, payload, payload_hash, prev_hash)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (entry_id, timestamp, entry_type, json.dumps(payload), payload_hash, prev_hash))
    
    seq_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return AuditEntry(
        entry_id=entry_id,
        timestamp=timestamp,
        entry_type=entry_type,
        payload=payload,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        seq_id=seq_id
    )

def verify_chain(db_path: str = DB_PATH) -> tuple[bool, Optional[str]]:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT entry_id, payload, payload_hash, prev_hash FROM entries ORDER BY seq_id ASC")
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        # DB doesn't exist or table doesn't exist
        return True, None
        
    expected_prev = "GENESIS"
    
    for row in rows:
        entry_id, payload_str, stored_hash, stored_prev = row
        
        # 1. Recompute and check payload hash
        payload = json.loads(payload_str)
        recomputed_hash = _hash_payload(payload)
        
        if recomputed_hash != stored_hash:
            return False, entry_id
            
        # 2. Check prev hash chain
        if stored_prev != expected_prev:
            return False, entry_id
            
        expected_prev = stored_hash
        
    return True, None

def get_chain_for_clause(clause_id: str, db_path: str = DB_PATH) -> list[AuditEntry]:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # In a real app we'd query by extracting JSON, but here we can use LIKE 
        # or parse all rows since it's a simple hackathon build
        cursor.execute("SELECT * FROM entries ORDER BY seq_id ASC")
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return []
        
    results = []
    for row in rows:
        seq_id, entry_id, timestamp, entry_type, payload_str, payload_hash, prev_hash = row
        payload = json.loads(payload_str)
        
        # Look for the clause_id anywhere in the payload
        if payload.get("clause_id") == clause_id:
            results.append(AuditEntry(
                entry_id=entry_id,
                timestamp=timestamp,
                entry_type=entry_type,
                payload=payload,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                seq_id=seq_id
            ))
            
    return results
