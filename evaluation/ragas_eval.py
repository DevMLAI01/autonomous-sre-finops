"""
Ragas Evaluation Suite
Runs automated quality checks on the RAG pipeline.
Must pass Faithfulness >= 0.85 and Answer Relevance >= 0.85 before deployment.

Usage:
    python -m evaluation.ragas_eval
"""
from __future__ import annotations

import json
import sys
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import AnswerRelevancy

from agents.llm_client import get_llm, get_embeddings
from rag.retriever import assess_resource
from config import cfg


# ── Evaluation dataset ────────────────────────────────────────────────────────
# These are representative test cases with known expected answers.
# In CI/CD, expand this with a larger golden dataset.
EVAL_CASES = [
    {
        "resource": {
            "instance_id": "i-test001",
            "instance_type": "m5.xlarge",
            "tags": {
                "Name": "legacy-batch-processor",
                "Project": "data-migration-2022",
                "Environment": "production",
            },
            "average_cpu_percent": 0.8,
            "estimated_monthly_cost_usd": 145.0,
        },
        "question": "Is this EC2 instance actively needed by any current project?",
        "ground_truth": "The data-migration-2022 project is complete. This instance is orphaned and safe to decommission.",
    },
    {
        "resource": {
            "instance_id": "i-test002",
            "instance_type": "c5.2xlarge",
            "tags": {
                "Name": "load-test-standby",
                "Project": "q4-performance-testing",
                "Environment": "staging",
                "ProtectedUntil": "2026-06-01",
            },
            "average_cpu_percent": 1.2,
            "estimated_monthly_cost_usd": 220.0,
        },
        "question": "Is this EC2 instance actively needed by any current project?",
        "ground_truth": "This instance is reserved for Q4 performance testing and is protected until 2026-06-01. Do not decommission.",
    },
    {
        "resource": {
            "instance_id": "i-test003",
            "instance_type": "t3.large",
            "tags": {
                "Name": "old-dev-sandbox",
                "Project": "unknown",
                "Environment": "development",
                "Team": "backend",
            },
            "average_cpu_percent": 2.1,
            "estimated_monthly_cost_usd": 110.0,
        },
        "question": "Is this EC2 instance actively needed by any current project?",
        "ground_truth": "No project documentation references this sandbox. It appears to be an abandoned development instance.",
    },
]


def _build_ragas_dataset(eval_cases: list[dict]) -> Dataset:
    """Run the RAG pipeline on each test case and collect outputs."""
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for case in eval_cases:
        resource = case["resource"]
        question = case["question"]
        gt = case["ground_truth"]

        print(f"[ragas_eval] Evaluating {resource['instance_id']}...")
        assessment = assess_resource(resource)

        questions.append(question)
        answers.append(f"{assessment['status']}: {assessment['reason']}")
        contexts.append(assessment.get("context_chunks", ["No context retrieved."]))
        ground_truths.append(gt)

    return Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })


def run_evaluation() -> dict[str, float]:
    """
    Run Ragas evaluation and return metric scores.
    Exits with code 1 if scores are below thresholds.
    """
    print("[ragas_eval] Building evaluation dataset...")
    dataset = _build_ragas_dataset(EVAL_CASES)

    print("[ragas_eval] Running Ragas metrics (faithfulness + answer_relevancy)...")
    ragas_llm = LangchainLLMWrapper(get_llm())
    ragas_emb = LangchainEmbeddingsWrapper(get_embeddings())
    results = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(llm=ragas_llm), AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb)],
    )

    scores = results.to_pandas()[["faithfulness", "answer_relevancy"]].mean().to_dict()

    print("\n" + "=" * 50)
    print("RAGAS EVALUATION RESULTS")
    print("=" * 50)
    print(f"  Faithfulness    : {scores['faithfulness']:.3f}  (min: {cfg.RAGAS_MIN_FAITHFULNESS})")
    print(f"  Answer Relevance: {scores['answer_relevancy']:.3f}  (min: {cfg.RAGAS_MIN_ANSWER_RELEVANCE})")

    passed = True
    if scores["faithfulness"] < cfg.RAGAS_MIN_FAITHFULNESS:
        print(f"\n  FAIL: Faithfulness {scores['faithfulness']:.3f} < {cfg.RAGAS_MIN_FAITHFULNESS}")
        passed = False
    if scores["answer_relevancy"] < cfg.RAGAS_MIN_ANSWER_RELEVANCE:
        print(f"\n  FAIL: Answer Relevance {scores['answer_relevancy']:.3f} < {cfg.RAGAS_MIN_ANSWER_RELEVANCE}")
        passed = False

    if passed:
        print("\n  PASS: All metrics meet the quality gate threshold.")
    print("=" * 50 + "\n")

    if not passed:
        sys.exit(1)

    return scores


if __name__ == "__main__":
    run_evaluation()
