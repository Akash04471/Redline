import streamlit as st
import json
import uuid

# --- Layout Configuration ---
st.set_page_config(page_title="Redline Consensus Engine", layout="wide")

# --- Imports from Backend ---
from src.db.client import get_qdrant_client
from src.config import COLLECTION_COMPLIANCE, COLLECTION_HISTORICAL, COLLECTION_RISK, set_fault
from src.engine.workflow import run_workflow
from src.agents.human_review import capture_human_decision
from src.scripts.compliance_sweep import run_sweep
from src.engine.audit import verify_chain, get_chain_for_clause
import sqlite3

# --- Data Fetching ---
@st.cache_data(ttl=300)
def get_dropdown_options():
    client = get_qdrant_client()
    def extract_unique(collection, field):
        try:
            points, _ = client.scroll(collection_name=collection, limit=1000, with_payload=True, with_vectors=False)
            vals = [p.payload.get(field) for p in points if p.payload and p.payload.get(field)]
            return sorted(list(set(vals)))
        except Exception:
            return ["Unknown"]
            
    return {
        "jurisdiction": extract_unique(COLLECTION_COMPLIANCE, "jurisdiction"),
        "regulation_type": extract_unique(COLLECTION_COMPLIANCE, "regulation_type"),
        "contract_type": extract_unique(COLLECTION_HISTORICAL, "contract_type"),
        "clause_category": extract_unique(COLLECTION_HISTORICAL, "clause_category"),
        "industry": extract_unique(COLLECTION_RISK, "industry")
    }

def get_metrics():
    try:
        conn = sqlite3.connect("audit.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM entries WHERE entry_type = 'consensus_decision'")
        total_evals = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM entries WHERE entry_type = 'consensus_decision' AND payload LIKE '%\"consensus\": true%'")
        consensus_true = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM entries WHERE entry_type = 'human_decision'")
        total_reviews = cursor.fetchone()[0]
        
        cursor.execute("SELECT payload FROM entries WHERE entry_type = 'consensus_decision'")
        rows = cursor.fetchall()
        tiers = {}
        for r in rows:
            data = json.loads(r[0])
            tier = data.get("output", {}).get("escalation_tier", "unknown")
            if tier != "none":
                tiers[tier] = tiers.get(tier, 0) + 1
            
        conn.close()
        return {
            "processed": total_evals,
            "consensus_rate": f"{(consensus_true/total_evals*100):.1f}%" if total_evals > 0 else "0%",
            "reviews": total_reviews,
            "escalations": tiers
        }
    except Exception as e:
        return {"processed": 0, "consensus_rate": "0%", "reviews": 0, "escalations": {}}

# --- Session State Management ---
if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
if "clause_id" not in st.session_state:
    st.session_state.clause_id = None
if "sweep_result" not in st.session_state:
    st.session_state.sweep_result = None

# --- Main App ---
st.title("⚖️ Redline Consensus Engine")

tab1, tab2, tab3, tab4 = st.tabs(["Clause Review", "Fault Injection Demo", "Compliance Sweep", "Audit & Metrics"])

options = get_dropdown_options()

with tab1:
    st.header("Clause Review Workflow")
    
    with st.form("clause_review_form"):
        clause_text = st.text_area("Clause Text", height=150)
        c1, c2, c3, c4 = st.columns(4)
        jurisdiction = c1.selectbox("Jurisdiction", options["jurisdiction"])
        contract_type = c2.selectbox("Contract Type", options["contract_type"])
        clause_type = c3.selectbox("Clause Category", options["clause_category"])
        industry = c4.selectbox("Industry", options["industry"])
        
        submitted = st.form_submit_button("Run Analysis", type="primary")
        
    if submitted and clause_text:
        with st.spinner("Agents are analyzing the clause..."):
            clause_id = str(uuid.uuid4())
            st.session_state.clause_id = clause_id
            
            clause_data = {
                "clause_id": clause_id,
                "clause_text": clause_text,
                "jurisdiction": jurisdiction,
                "contract_type": contract_type,
                "clause_category": clause_type,
                "clause_type": clause_type, # Using same for commercial agent
                "industry": industry
            }
            
            result = run_workflow(clause_data)
            st.session_state.workflow_result = result

    # Display Results if we have them
    if st.session_state.workflow_result:
        res = st.session_state.workflow_result
        raw = res.raw_outputs
        cons = res.consensus_decision.model_dump() if hasattr(res.consensus_decision, "model_dump") else res.consensus_decision
        
        st.subheader("Agent Analysis")
        colA, colB, colC = st.columns(3)
        
        with colA:
            st.markdown("#### 🏛️ Regulatory Agent")
            st.json(raw.get("regulatory", {}))
            
        with colB:
            st.markdown("#### 💼 Commercial Agent")
            st.json(raw.get("commercial", {}))
            
        with colC:
            st.markdown("#### 📚 Precedent Agent")
            st.json(raw.get("precedent", {}))
            
        st.divider()
        st.subheader("Engine Consensus")
        routing = cons.get("routing_decision")
        if routing == "auto_recommend":
            st.success(f"**Auto-Recommend** - {cons.get('summary')}")
            st.markdown("##### 📝 Suggested Redline:")
            rec = res.branch_outcome
            st.info(rec.get("redline_suggestion", "No suggestion provided."))
            st.markdown("**Rationale:** " + rec.get("explanation", ""))
            
        elif routing == "human_escalate":
            st.error(f"**Escalated to Human** - {cons.get('summary')}")
            st.markdown(f"**Tier:** `{cons.get('escalation_tier')}`")
            
            with st.expander("Human Review Package", expanded=True):
                st.write("**Original Text:**")
                st.write(clause_text if clause_text else "No text provided.")
                
                rev_decision = st.radio("Review Decision", ["Approved", "Rejected", "Approved with Changes"])
                rev_rationale = st.text_area("Rationale")
                rev_final_text = st.text_area("Final Edited Text (if changes made)")
                
                if st.button("Submit Decision"):
                    capture_human_decision(
                        clause_id=st.session_state.clause_id,
                        clause_text=clause_text if clause_text else "",
                        decision=rev_decision,
                        final_text=rev_final_text,
                        rationale=rev_rationale,
                        reviewer_id="human_user_1"
                    )
                    st.success("Decision recorded and saved to Precedents!")
                    st.session_state.workflow_result = None # Reset
                    
        st.divider()
        with st.expander("View Audit Chain for this Clause"):
            chain = get_chain_for_clause(st.session_state.clause_id)
            if not chain:
                st.write("No audit records found.")
            for entry in chain:
                st.markdown(f"**{entry.timestamp}** | `{entry.entry_type}`")
                st.json(entry.payload)


with tab2:
    st.header("Fault Injection Demo")
    st.write("Demonstrate system resilience by forcing an expert agent to fail.")
    
    col1, col2 = st.columns(2)
    target_agent = col1.selectbox("Target Agent", ["regulatory", "commercial", "precedent"])
    fault_mode = col2.selectbox("Fault Mode", ["crash", "timeout", "malformed"])
    
    c_btn1, c_btn2 = st.columns([1, 4])
    if c_btn1.button("Inject Fault & Run", type="primary"):
        set_fault(target_agent, fault_mode)
        st.warning(f"Injected '{fault_mode}' into {target_agent} agent.")
        
        # Use dummy data to trigger the workflow
        clause_id = str(uuid.uuid4())
        st.session_state.clause_id = clause_id
        
        clause_data = {
            "clause_id": clause_id,
            "clause_text": "Standard indemnification clause with $1M cap.",
            "jurisdiction": "US",
            "contract_type": "MSA",
            "clause_category": "Indemnification",
            "clause_type": "Indemnification", 
            "industry": "Technology"
        }
        
        with st.spinner("Running faulted workflow..."):
            result = run_workflow(clause_data)
            st.session_state.workflow_result = result
            
        set_fault(target_agent, None) # Clear immediately
        st.success("Workflow completed safely.")
        st.info("Check the Clause Review tab to see how the Engine escalated the failure!")
        
    if c_btn2.button("Reset Faults"):
        set_fault("regulatory", None)
        set_fault("commercial", None)
        set_fault("precedent", None)
        st.success("All faults cleared.")


with tab3:
    st.header("Compliance Sweep")
    st.write("Introduce a new regulatory policy and sweep historical clauses to identify new compliance risks.")
    
    with st.form("sweep_form"):
        new_policy = st.text_area("New Policy Text", "Upon request, providers must delete personal data within 15 days of notice, no exceptions.")
        colA, colB = st.columns(2)
        sw_jur = colA.selectbox("Jurisdiction", options["jurisdiction"], key="sw_jur")
        sw_reg = colB.text_input("Regulation Type", "GDPR-Strict")
        
        sweep_btn = st.form_submit_button("Run Sweep", type="primary")
        
    if sweep_btn:
        with st.spinner("Sweeping historical clauses against new policy..."):
            res = run_sweep(new_policy, sw_jur, sw_reg)
            st.session_state.sweep_result = res
            
    if st.session_state.sweep_result:
        res = st.session_state.sweep_result
        st.subheader("Sweep Results")
        
        m1, m2 = st.columns(2)
        m1.metric("Historically Relevant Clauses Scanned", res.total_scanned)
        m2.metric("Newly Flagged as High Risk", res.total_flagged)
        
        if res.total_flagged > 0:
            st.markdown("### Flagged Clauses")
            for fc in res.flagged_clauses:
                with st.expander(f"Clause: {fc.clause_id}"):
                    st.write(f"**Text:** {fc.clause_text}")
                    st.error(f"**Violation:** {fc.violation_reason}")
                    st.write(f"**New Risk Level:** {fc.risk_level}")


with tab4:
    st.header("Audit & Metrics")
    
    colA, colB = st.columns([1, 1])
    
    with colA:
        st.subheader("Blockchain-Style Audit Ledger")
        st.write("Verify the cryptographic integrity of all decisions in the system.")
        if st.button("Verify Full Audit Chain", type="primary"):
            with st.spinner("Verifying SHA-256 hash chain..."):
                is_valid, broken_id = verify_chain()
                if is_valid:
                    st.success("✅ Audit chain verified! No tampering detected.")
                else:
                    st.error(f"🚨 Tampering detected! Broken hash chain at entry: {broken_id}")
                    
    with colB:
        st.subheader("System Metrics (KPIs)")
        metrics = get_metrics()
        
        st.metric("Total Clauses Processed", metrics["processed"])
        st.metric("Consensus Rate", metrics["consensus_rate"])
        st.metric("Human Review Entries Captured", metrics["reviews"])
        
        st.markdown("#### Escalations by Tier")
        tiers = metrics["escalations"]
        if tiers:
            for k, v in tiers.items():
                st.write(f"- **{k}**: {v}")
        else:
            st.write("No escalations yet.")
