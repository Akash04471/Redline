"""
UI-Level Role Simulation (For Demo Purposes Only)
This file implements a simple UI-based role selector to demonstrate the Role-Based Access Control (RBAC) 
concept from the PRD. In a production environment, authorization would be enforced server-side 
via OPA (Open Policy Agent) policies (per PRD Section 11), ensuring that users cannot simply 
bypass restrictions by modifying frontend code.
"""
import streamlit as st
import json
import uuid

# --- Layout Configuration ---
st.set_page_config(page_title="Redline Consensus Engine", page_icon="⚖️", layout="wide")

# --- CSS Injection ---
st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Lora:ital,wght@0,400;0,600;1,400&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Lora', serif !important;
    color: #ffffff !important;
}

/* Agent Nameplate */
.agent-nameplate {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #ffffff;
    border-bottom: 2px solid #ffffff;
    padding-bottom: 5px;
    margin-bottom: 10px;
}

/* Consensus Ruling */
.badge-verified {
    display: inline-block;
    background-color: #b8903c;
    color: #fff;
    padding: 6px 12px;
    font-weight: bold;
    font-size: 0.85rem;
    letter-spacing: 1px;
}

.badge-critical {
    display: inline-block;
    background-color: #d32f2f;
    color: #fff;
    padding: 6px 12px;
    font-weight: bold;
    font-size: 0.85rem;
    letter-spacing: 1px;
}

/* Audit Ledger */
.audit-chain-link {
    font-family: monospace;
    color: #ffffff;
    background: #2d3748;
    padding: 4px 8px;
    border-left: 4px solid #ffffff;
    margin: 5px 0 15px 15px;
    position: relative;
    font-size: 0.85rem;
}

.audit-chain-link::before {
    content: "⛓";
    position: absolute;
    left: -22px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
}
</style>
''', unsafe_allow_html=True)



# --- Imports from Backend ---
from src.db.client import get_qdrant_client
from src.config import COLLECTION_COMPLIANCE, COLLECTION_HISTORICAL, COLLECTION_RISK, set_fault
from src.engine.workflow import run_workflow, run_batch_workflow
from src.parsing.extractor import extract_text, split_into_clauses, ClauseCandidate
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
if "extracted_clauses" not in st.session_state:
    st.session_state.extracted_clauses = None
if "batch_result" not in st.session_state:
    st.session_state.batch_result = None

# --- Main App ---

st.markdown('''
<div style="text-align: center; border-bottom: 2px solid #ffffff; padding-bottom: 20px; margin-bottom: 20px;">
    <h1 style="font-size: 2.5rem; margin-bottom: 5px;">⚖️ Redline Consensus Engine</h1>
    <p style="font-style: italic; color: #ffffff; font-family: 'Lora', serif; font-size: 1.2rem;">3 independent AI reviewers, reconciled by rule-based consensus, logged to a tamper-evident ledger.</p>
</div>
''', unsafe_allow_html=True)



with st.sidebar:
    st.header("Role Simulation")
    active_role = st.selectbox("View as role", ["Legal Counsel", "Compliance Officer", "Legal Ops Admin", "Auditor"])
    st.markdown(f'<div style="background-color: #333333; color: #fff; padding: 5px 10px; text-transform: uppercase; font-size: 0.8rem; font-weight: bold; text-align: center; letter-spacing: 1px; margin-top: 10px;">CREDENTIAL ID: {active_role}</div>', unsafe_allow_html=True)

tab_names = []
if active_role == "Legal Counsel":
    tab_names = ["📋 Clause Review"]
elif active_role == "Compliance Officer":
    tab_names = ["📋 Clause Review", "🔍 Compliance Sweep"]
elif active_role == "Legal Ops Admin":
    tab_names = ["⚠ Resilience Test", "🔐 Audit Ledger"]
elif active_role == "Auditor":
    tab_names = ["🔐 Audit Ledger"]

tabs = st.tabs(tab_names)
tab_dict = dict(zip(tab_names, tabs))

options = get_dropdown_options()

if "📋 Clause Review" in tab_dict:
    with tab_dict["📋 Clause Review"]:
        st.header("Clause Review Workflow")
    
        input_mode = st.radio("Input Mode", ["Manual Single Clause", "Full Document Upload"], horizontal=True)
    
        if input_mode == "Manual Single Clause":
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
                has_dp = "data_privacy" in raw
                if has_dp:
                    colA, colB, colC, colD = st.columns(4)
                else:
                    colA, colB, colC = st.columns(3)
            
                with colA:
                    st.markdown('<div class="agent-nameplate">🏛️ Senior Regulatory Officer</div>', unsafe_allow_html=True)
                    st.json(raw.get("regulatory", {}))
                
                with colB:
                    st.markdown('<div class="agent-nameplate">💼 Commercial Risk Analyst</div>', unsafe_allow_html=True)
                    st.json(raw.get("commercial", {}))
                
                with colC:
                    st.markdown('<div class="agent-nameplate">📚 Precedent Records Clerk</div>', unsafe_allow_html=True)
                    st.json(raw.get("precedent", {}))
                
                if has_dp:
                    with colD:
                        st.markdown('<div class="agent-nameplate">🛡️ Data Protection Officer</div>', unsafe_allow_html=True)
                        st.json(raw.get("data_privacy", {}))
                
                st.divider()
                st.subheader("Engine Consensus")
                routing = cons.get("routing_decision")
                if routing == "auto_recommend":
                    st.markdown(f'<div class="badge-verified">APPROVED / AUTO-RECOMMEND</div>', unsafe_allow_html=True)
                    st.markdown(f"**Ruling:** {cons.get('summary')}")
                    st.markdown("##### 📝 Suggested Redline:")
                    rec = res.branch_outcome
                    st.markdown(f"> {rec.get('redline_suggestion', 'No suggestion provided.')}")
                    st.markdown(f"**Rationale:** {rec.get('explanation', '')}")
                
                elif routing == "human_escalate":
                    st.markdown(f'<div class="badge-critical">ESCALATED TO HUMAN</div>', unsafe_allow_html=True)
                    st.markdown(f"**Tier:** `{cons.get('escalation_tier')}`")
                    st.markdown(f"**Ruling:** {cons.get('summary')}")
                
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
                        st.markdown(f'<div class="audit-chain-link"><b>{entry.timestamp}</b> | {entry.entry_type}<br/>HASH: {entry.entry_id}</div>', unsafe_allow_html=True)
                        st.json(entry.payload)
    
        else:
            # Full Document Upload Mode
            uploaded_file = st.file_uploader("Upload Contract (PDF or DOCX)", type=["pdf", "docx"])
            c1, c2, c3 = st.columns(3)
            batch_jur = c1.selectbox("Jurisdiction", options["jurisdiction"], key="b_jur")
            batch_con = c2.selectbox("Contract Type", options["contract_type"], key="b_con")
            batch_ind = c3.selectbox("Industry", options["industry"], key="b_ind")
        
            if uploaded_file is not None:
                if st.button("Extract Clauses"):
                    with st.spinner("Extracting and splitting text..."):
                        raw_text = extract_text(uploaded_file.read(), uploaded_file.name)
                        clauses = split_into_clauses(raw_text)
                        st.session_state.extracted_clauses = [c.model_dump() for c in clauses]
                        st.session_state.batch_result = None
            
                if st.session_state.extracted_clauses:
                    st.subheader("Extracted Clauses Preview")
                    st.write("Review the heuristically split clauses below. You can edit the text or category before running the workflow.")
                    edited_clauses = st.data_editor(st.session_state.extracted_clauses, num_rows="dynamic", use_container_width=True)
                
                    if st.button("Run Full Document Review", type="primary"):
                        with st.spinner(f"Running batch workflow on {len(edited_clauses)} clauses (this may take a minute)..."):
                            # Convert back to objects
                            c_objs = [ClauseCandidate(**c) for c in edited_clauses]
                            res, summary = run_batch_workflow(c_objs, batch_jur, batch_con, batch_ind)
                            st.session_state.batch_result = {"results": res, "summary": summary}
                        
                if st.session_state.batch_result:
                    st.subheader("Batch Review Results")
                    summary = st.session_state.batch_result["summary"]
                    st.info(f"**Document Summary:** {summary['total_processed']} clauses processed. {summary['auto_recommended']} auto-recommended, {summary['escalated']} escalated.")
                    if summary["tiers"]:
                        st.write("**Escalation Breakdown:**")
                        st.json(summary["tiers"])
                
                    st.divider()
                    results = st.session_state.batch_result["results"]
                    for r in results:
                        clause_obj = r["clause"]
                        w_res = r["result"]
                        cons = w_res.consensus_decision.model_dump() if hasattr(w_res.consensus_decision, "model_dump") else w_res.consensus_decision
                    
                        routing = cons.get('routing_decision')
                        emoji = "✅" if routing == "auto_recommend" else "⚠️"
                    
                        with st.expander(f"{emoji} Clause {clause_obj.clause_index} | {clause_obj.clause_category} | {routing}"):
                            st.write("**Text:**", clause_obj.raw_text)
                        
                            if routing == "auto_recommend":
                                st.markdown(f'<div class="badge-verified">APPROVED</div> **{cons.get("summary")}**', unsafe_allow_html=True)
                                rec = w_res.branch_outcome
                                st.markdown(f'> {rec.get("redline_suggestion", "No suggestion provided.")}')
                            else:
                                st.markdown(f'<div class="badge-critical">ESCALATED: {cons.get("escalation_tier", "none")}</div> **{cons.get("summary")}**', unsafe_allow_html=True)
                            
                            st.json(cons)


if "⚠ Resilience Test" in tab_dict:
    with tab_dict["⚠ Resilience Test"]:
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


if "🔍 Compliance Sweep" in tab_dict:
    with tab_dict["🔍 Compliance Sweep"]:
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
                        st.markdown(f'<div class="badge-critical">VIOLATION DETECTED</div>', unsafe_allow_html=True)
                        st.write(f"**Reason:** {fc.violation_reason}")
                        st.write(f"**New Risk Level:** {fc.risk_level}")


if "🔐 Audit Ledger" in tab_dict:
    with tab_dict["🔐 Audit Ledger"]:
        st.header("Audit & Metrics")
    
        colA, colB = st.columns([1, 1])
    
        with colA:
            st.subheader("Blockchain-Style Audit Ledger")
            st.write("Verify the cryptographic integrity of all decisions in the system.")
            if st.button("Verify Full Audit Chain", type="primary"):
                with st.spinner("Verifying SHA-256 hash chain..."):
                    is_valid, broken_id = verify_chain()
                    if is_valid:
                        st.markdown('<div class="badge-verified">✅ AUDIT CHAIN VERIFIED: NO TAMPERING DETECTED</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="badge-critical">🚨 TAMPERING DETECTED! BROKEN HASH CHAIN AT: {broken_id}</div>', unsafe_allow_html=True)
                    
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