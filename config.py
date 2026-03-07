"""Central configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # LLM
    GOOGLE_API_KEY: str = os.environ["GOOGLE_API_KEY"]
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"

    # LangSmith
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "true")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "autonomous-sre-finops")

    # AWS
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_DEFAULT_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # GitHub
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "")
    GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "")

    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "sre_docs")

    # Thresholds
    CPU_UTILIZATION_THRESHOLD: float = float(os.getenv("CPU_UTILIZATION_THRESHOLD", "5.0"))
    MONTHLY_COST_THRESHOLD: float = float(os.getenv("MONTHLY_COST_THRESHOLD", "100.0"))
    LOOKBACK_DAYS: int = int(os.getenv("LOOKBACK_DAYS", "7"))

    # Notifications
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")
    NOTIFICATION_EMAIL: str = os.getenv("NOTIFICATION_EMAIL", "")

    # Ragas quality gate
    RAGAS_MIN_FAITHFULNESS: float = 0.85
    RAGAS_MIN_ANSWER_RELEVANCE: float = 0.85


cfg = Config()
