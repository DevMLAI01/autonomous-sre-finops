"""
Gemini 1.5 Pro LLM client with LangSmith tracing baked in.

Usage:
    from agents.llm_client import get_llm, get_embeddings
    llm = get_llm()
    embeddings = get_embeddings()
"""
import os
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from config import cfg

# Ensure LangSmith env vars are set before any LangChain import
os.environ["LANGCHAIN_TRACING_V2"] = cfg.LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_PROJECT"] = cfg.LANGCHAIN_PROJECT
if cfg.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = cfg.LANGCHAIN_API_KEY


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """Return a traced Gemini 1.5 Pro chat model."""
    return ChatGoogleGenerativeAI(
        model=cfg.GEMINI_MODEL,
        google_api_key=cfg.GOOGLE_API_KEY,
        temperature=temperature,
    )


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Return Gemini embedding model for Qdrant ingestion."""
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=cfg.GOOGLE_API_KEY,
    )
