import asyncio
from pydantic import BaseModel
from typing import Any, Dict
from lyzr_automata import Task, LinearSyncPipeline

from src.agents.regulatory import regulatory_agent
from src.agents.commercial import commercial_risk_agent
from src.agents.precedent import precedent_agent
from src.engine.consensus import evaluate_consensus
from src.engine.audit import append_entry

class WorkflowResult(BaseModel):
    raw_outputs: Dict[str, Any]
    consensus_decision: Dict[str, Any]
    branch_outcome: Dict[str, Any]

class ParallelExecutionTask(Task):
    """
    Custom Lyzr Task that overrides the execute method to run the three specialist
    agents in parallel using asyncio, wrapping the IO-bound LLM calls to ensure concurrency 
    while keeping Lyzr as the orchestration layer of record.
    """
    def __init__(self, clause_data: dict):
        super().__init__(name="parallel_agent_execution", model=None) # type: ignore
        self.clause_data = clause_data
        
    async def _run_agents(self):
        cd = self.clause_data
        # asyncio.to_thread wrappers since the agents are currently synchronous
        r_task = asyncio.to_thread(regulatory_agent, cd['clause_text'], cd['jurisdiction'], cd['contract_type'], cd['clause_id'])
        c_task = asyncio.to_thread(commercial_risk_agent, cd['clause_text'], cd['clause_type'], cd['industry'], cd['clause_id'])
        p_task = asyncio.to_thread(precedent_agent, cd['clause_text'], cd['clause_category'], cd['clause_id'])
        
        reg_res, com_res, prec_res = await asyncio.gather(r_task, c_task, p_task)
        return {
            "regulatory": reg_res,
            "commercial": com_res,
            "precedent": prec_res
        }
        
    def execute(self, *args, **kwargs) -> dict:
        return asyncio.run(self._run_agents())

class ConsensusTask(Task):
    def __init__(self, clause_id: str):
        super().__init__(name="consensus_evaluation", model=None) # type: ignore
        self.clause_id = clause_id
        
    def execute(self, input_data: dict, *args, **kwargs) -> dict:
        # Evaluate consensus which also automatically logs to audit.db
        decision = evaluate_consensus(
            regulatory=input_data["regulatory"],
            commercial=input_data["commercial"],
            precedent=input_data["precedent"],
            clause_id=self.clause_id
        )
        return decision.model_dump()

from src.agents.recommendation import recommendation_agent
from src.agents.human_review import human_review_agent

class BranchingTask(Task):
    def __init__(self, clause_data: dict, raw_outputs: dict):
        super().__init__(name="workflow_branching", model=None) # type: ignore
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
    Executes the full pipeline using Lyzr Automata primitives.
    """
    clause_id = clause_data["clause_id"]
    
    # Instantiate tasks
    t1 = ParallelExecutionTask(clause_data)
    t2 = ConsensusTask(clause_id)
    # We will execute the tasks sequentially via standard python calls for data passing,
    # as Lyzr Pipeline usually handles string prompt passing via LLMs rather than dict pipelines natively,
    # but we are using Task primitives as requested to organize the nodes.
    
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
