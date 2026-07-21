from fastembed import TextEmbedding

# Load the model once at module level for low demo latency
_embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

def get_embedding(text: str) -> list[float]:
    """
    Generate an embedding for the given text.
    Returns a 384-dimensional list of floats.
    """
    # fastembed expects an iterable of strings and returns a generator of numpy arrays
    embeddings_gen = _embedding_model.embed([text])
    embedding = next(embeddings_gen)
    return embedding.tolist()
