import os
import json
from pydantic import BaseModel
from google import genai
from google.genai import types
from src.engine.audit import append_entry

class RecommendationOutput(BaseModel):
    suggested_redline_text: str
    plain_language_rationale: str
    confidence_score: float
    cited_sources: list[str]

def recommendation_agent(clause_text: str, agent_outputs: dict, clause_id: str = "unknown") -> dict:
    """
    Agent for proposing redlines on clauses that achieved consensus.
    Role: Senior Legal Drafter
    """
    try:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("No API key was provided.")
            
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        You are a Senior Legal Drafter. Your goal is to provide a clean redline recommendation for a clause.
        
        Original Clause:
        {clause_text}
        
        Expert Assessments:
        {json.dumps(agent_outputs, indent=2)}
        
        Provide a revised redline text, a plain language rationale for the change, a confidence score (0-1), 
        and a list of cited sources (e.g. IDs of any regulations, precedent clauses, or risk policies mentioned by the experts).
        Respond ONLY in JSON.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RecommendationOutput,
                temperature=0.2,
            ),
        )
        
        output_text = response.text
        if not output_text:
            raise ValueError("Empty response from LLM")
            
        parsed_json = json.loads(output_text)
        validated_output = RecommendationOutput(**parsed_json)
        output_dict = validated_output.model_dump()
        
        append_entry("agent_verdict", {
            "agent": "recommendation",
            "clause_id": clause_id,
            "output": output_dict
        })
        return output_dict
        
    except Exception as e:
        output_dict = {
            "agent_failed": True,
            "suggested_redline_text": "Failed to generate recommendation.",
            "plain_language_rationale": f"Agent failed: {str(e)}",
            "confidence_score": 0.0,
            "cited_sources": []
        }
        append_entry("agent_verdict", {
            "agent": "recommendation",
            "clause_id": clause_id,
            "output": output_dict
        })
        return output_dict
