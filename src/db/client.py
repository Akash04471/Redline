from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType
from src.config import QDRANT_URL, QDRANT_API_KEY

# Qdrant client singleton
client = QdrantClient(path=QDRANT_URL) if "http" not in QDRANT_URL else QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def get_qdrant_client():
    return client

def create_collections():
    collections = {
        "compliance_policies": ["jurisdiction", "regulation_type"],
        "historical_clauses": ["contract_type", "clause_category"],
        "risk_positions": ["clause_type", "industry"],
        "review_feedback": []
    }
    
    vector_size = 384  # Matches BAAI/bge-small-en-v1.5
    
    for collection_name, payload_fields in collections.items():
        if not client.collection_exists(collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            
            # Enable payload indexing
            for field in payload_fields:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD
                )
