"""
RAG Retriever
Queries Qdrant using resource tags and instance metadata to determine
whether a flagged resource is protected, active, or orphaned.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_qdrant import QdrantVectorStore

from agents.llm_client import get_embeddings, get_llm
from config import cfg


RETRIEVER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an SRE context analyst. Given internal documentation excerpts and an AWS resource's metadata,
determine whether this resource is:
- PROTECTED: actively needed (e.g., reserved for a load test, disaster recovery standby, etc.)
- ORPHANED: safe to decommission (no active project, forgotten resource, etc.)

Be conservative — if there is ANY indication the resource might be needed, mark it as PROTECTED.
Reply with a JSON object: {{"status": "PROTECTED"|"ORPHANED", "reason": "<one sentence explanation>", "confidence": 0.0-1.0}}""",
    ),
    (
        "human",
        """Resource metadata:
{resource_metadata}

Relevant documentation excerpts:
{context}

What is the status of this resource?""",
    ),
])


def _get_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        url=cfg.QDRANT_URL,
        api_key=cfg.QDRANT_API_KEY,
        collection_name=cfg.QDRANT_COLLECTION,
    )


def build_query_from_resource(resource: dict) -> str:
    """Construct a natural language query from resource tags and metadata."""
    tags = resource.get("tags", {})
    parts = [
        f"instance {resource.get('instance_id', '')}",
        f"type {resource.get('instance_type', '')}",
    ]
    if "Name" in tags:
        parts.append(f"name: {tags['Name']}")
    if "Project" in tags:
        parts.append(f"project: {tags['Project']}")
    if "Environment" in tags:
        parts.append(f"environment: {tags['Environment']}")
    if "Team" in tags:
        parts.append(f"team: {tags['Team']}")

    return " ".join(parts)


def retrieve_context(resource: dict, top_k: int = 5) -> list[str]:
    """Retrieve the top-k most relevant document chunks for a resource."""
    query = build_query_from_resource(resource)
    store = _get_vector_store()
    docs = store.similarity_search(query, k=top_k)
    return [doc.page_content for doc in docs]


def assess_resource(resource: dict) -> dict:
    """
    Full RAG pipeline: retrieve docs → ask LLM → return assessment.

    Returns:
        {
            "status": "PROTECTED" | "ORPHANED",
            "reason": str,
            "confidence": float,
            "context_chunks": list[str],
        }
    """
    import json

    context_chunks = retrieve_context(resource)
    context_text = "\n\n---\n\n".join(context_chunks) if context_chunks else "No relevant documentation found."

    resource_metadata = json.dumps(resource, indent=2)

    llm = get_llm(temperature=0.0)
    chain = RETRIEVER_PROMPT | llm

    response = chain.invoke({
        "resource_metadata": resource_metadata,
        "context": context_text,
    })

    # Parse LLM JSON response safely
    try:
        # Strip markdown code fences if present
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        assessment = json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        # Fallback: treat as PROTECTED to avoid false positives
        assessment = {
            "status": "PROTECTED",
            "reason": "Could not parse LLM response — defaulting to PROTECTED for safety.",
            "confidence": 0.0,
        }

    assessment["context_chunks"] = context_chunks
    return assessment
