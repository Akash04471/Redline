import asyncio
from pydantic import BaseModel
from typing import Any, Dict

from src.agents.regulatory import regulatory_agent
from src.agents.commercial import commercial_risk_agent
from src.agents.precedent import precedent_agent
from src.agents.data_privacy import data_privacy_agent
from src.engine.consensus import evaluate_consensus
from src.engine.audit import append_entry

class WorkflowResult(BaseModel):
    raw_outputs: Dict[str, Any]
    consensus_decision: Dict[str, Any]
    branch_outcome: Dict[str, Any]

class ParallelExecutionTask:
    """
    Custom execution class that runs the three specialist
    agents in parallel using asyncio.
    """
    def __init__(self, clause_data: dict):
        self.clause_data = clause_data
        
    async def _run_agents(self):
        cd = self.clause_data
        # asyncio.to_thread wrappers since the agents are currently synchronous
        r_task = asyncio.to_thread(regulatory_agent, cd['clause_text'], cd['jurisdiction'], cd['contract_type'], cd['clause_id'])
        c_task = asyncio.to_thread(commercial_risk_agent, cd['clause_text'], cd['clause_type'], cd['industry'], cd['clause_id'])
        p_task = asyncio.to_thread(precedent_agent, cd['clause_text'], cd['clause_category'], cd['clause_id'])
        
        cat = cd.get('clause_category', '').lower()
        needs_dpo = any(k in cat for k in ["data processing", "data transfer", "data deletion", "data protection", "confidentiality", "privacy"])
        
        if needs_dpo:
            dp_task = asyncio.to_thread(data_privacy_agent, cd['clause_text'], cd['clause_id'])
            reg_res, com_res, prec_res, dp_res = await asyncio.gather(r_task, c_task, p_task, dp_task)
            return {
                "regulatory": reg_res,
                "commercial": com_res,
                "precedent": prec_res,
                "data_privacy": dp_res
            }
        else:
            reg_res, com_res, prec_res = await asyncio.gather(r_task, c_task, p_task)
            return {
                "regulatory": reg_res,
                "commercial": com_res,
                "precedent": prec_res
            }
        
    def execute(self, *args, **kwargs) -> dict:
        return asyncio.run(self._run_agents())

class ConsensusTask:
    def __init__(self, clause_id: str):
        self.clause_id = clause_id
        
    def execute(self, input_data: dict, *args, **kwargs) -> dict:
        # Evaluate consensus which also automatically logs to audit.db
        decision = evaluate_consensus(
            regulatory=input_data["regulatory"],
            commercial=input_data["commercial"],
            precedent=input_data["precedent"],
            clause_id=self.clause_id,
            data_privacy=input_data.get("data_privacy")
        )
        return decision.model_dump()

from src.agents.recommendation import recommendation_agent
from src.agents.human_review import human_review_agent

class BranchingTask:
    def __init__(self, clause_data: dict, raw_outputs: dict):
        self.clause_data = clause_data
        self.raw_outputs = raw_outputs
        
    def execute(self, consensus_data: dict, *args, **kwargs) -> dict:
        if consensus_data.get("consensus") is True:
            return self.recommendation_node(consensus_data)
        else:
            return self.human_review_node(consensus_data)
            
    def recommendation_node(self, consensus_data: dict) -> dict:
        return recommendation_agent(
            clause_text=self.clause_data["clause_text"],
            agent_outputs=self.raw_outputs,
            clause_id=self.clause_data["clause_id"]
        )
        
    def human_review_node(self, consensus_data: dict) -> dict:
        return human_review_agent(
            clause_id=self.clause_data["clause_id"],
            clause_text=self.clause_data["clause_text"],
            consensus_decision=consensus_data,
            raw_outputs=self.raw_outputs
        )

def run_workflow(clause_data: dict) -> WorkflowResult:
    """
    Executes the full pipeline.
    """
    clause_id = clause_data["clause_id"]
    
    # Instantiate tasks
    t1 = ParallelExecutionTask(clause_data)
    t2 = ConsensusTask(clause_id)
    
    raw_outputs = t1.execute()
    
    t3 = BranchingTask(clause_data, raw_outputs)
    
    consensus_decision = t2.execute(input_data=raw_outputs)
    branch_outcome = t3.execute(consensus_data=consensus_decision)
    
    result = WorkflowResult(
        raw_outputs=raw_outputs,
        consensus_decision=consensus_decision,
        branch_outcome=branch_outcome
    )
    
    return result

from src.parsing.extractor import ClauseCandidate

def run_batch_workflow(clauses: list[ClauseCandidate], jurisdiction: str, contract_type: str, industry: str):
    results = []
    summary = {
        "total_processed": 0,
        "auto_recommended": 0,
        "escalated": 0,
        "tiers": {}
    }
    
    import uuid
    contract_id = str(uuid.uuid4())
    
    for clause in clauses:
        clause_id = f"{contract_id}-clause-{clause.clause_index}"
        
        clause_data = {
            "clause_id": clause_id,
            "clause_text": clause.raw_text,
            "jurisdiction": jurisdiction,
            "contract_type": contract_type,
            "clause_category": clause.clause_category,
            "clause_type": clause.clause_category,
            "industry": industry
        }
        
        res = run_workflow(clause_data)
        results.append({"clause": clause, "result": res})
        
        summary["total_processed"] += 1
        
        cons = res.consensus_decision.model_dump() if hasattr(res.consensus_decision, "model_dump") else res.consensus_decision
        routing = cons.get("routing_decision")
        
        if routing == "auto_recommend":
            summary["auto_recommended"] += 1
        elif routing == "human_escalate":
            summary["escalated"] += 1
            tier = cons.get("escalation_tier", "unknown")
            summary["tiers"][tier] = summary["tiers"].get(tier, 0) + 1
            
    return results, summary
