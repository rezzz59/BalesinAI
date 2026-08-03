"""Run evaluation on synthetic dataset through the bot.

Usage:
    python scripts/run_evaluation.py --dataset /tmp/synthetic_dataset.csv --output /tmp/eval_results.csv
"""
import argparse
import csv
import sys
from typing import Any

# Add project to path
sys.path.insert(0, "/media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot")

from app.graph.graph import build_graph
from app.services.llm import MockLLMClient
from app.services.sheets import GoogleSheetsClient
from app.services.phone_gateway import PhoneGateway


def load_dataset(dataset_path: str) -> list[dict]:
    """Load evaluation dataset from CSV."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_evaluation(dataset: list[dict], output_path: str):
    """Run each message through the bot and record results."""
    # Initialize mock clients (no real LLM/Sheets/Gateway needed for testing)
    llm_client = MockLLMClient()
    sheets_client = None  # Will be None for messages without catalog lookup
    gateway = None  # Won't send actual messages
    
    # Build graph
    graph = build_graph(llm_client, sheets_client, gateway)
    
    results = []
    for i, test_case in enumerate(dataset):
        message = test_case.get("user_message", "").strip()
        expected_intent = test_case.get("expected_intent", "")
        
        if not message:
            # Skip empty messages
            continue
        
        # Run through graph
        state = {
            "tenant_id": "test",
            "wa_number": "+628123456789",
            "thread_id": "test_thread",
            "message_text": message,
            "messages": [],  # No history for now
        }
        
        try:
            result = graph.invoke(state)
            predicted_intent = result.get("intent", "unknown")
            predicted_response = result.get("reply_text", "")
            fallback_reason = result.get("fallback_reason", "")
            action = result.get("action", "")
            
            # Check if prediction matches expected
            passed = predicted_intent == expected_intent
            
            results.append({
                "test_id": test_case.get("test_id", f"test_{i}"),
                "user_message": message,
                "expected_intent": expected_intent,
                "predicted_intent": predicted_intent,
                "predicted_response": predicted_response[:200] if predicted_response else "",
                "fallback_reason": fallback_reason or "",
                "passed": str(passed),
                "notes": "",
            })
            
            status = "✅" if passed else "❌"
            print(f"{status} [{i+1}/{len(dataset)}] {message[:50]}...")
            if not passed:
                print(f"   Expected: {expected_intent}, Got: {predicted_intent}")
                
        except Exception as e:
            print(f"❌ Error on test {i+1}: {e}")
            results.append({
                "test_id": test_case.get("test_id", f"test_{i}"),
                "user_message": message,
                "expected_intent": expected_intent,
                "predicted_intent": "error",
                "predicted_response": "",
                "fallback_reason": str(e),
                "passed": "False",
                "notes": "Exception",
            })
    
    # Write results
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "test_id",
                "user_message",
                "expected_intent",
                "predicted_intent",
                "predicted_response",
                "fallback_reason",
                "passed",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(results)
    
    print()
    print(f"Results written to {output_path}")
    
    # Summary
    passed_count = sum(1 for r in results if r["passed"] == "True")
    total = len(results)
    print(f"Pass rate: {passed_count}/{total} ({100*passed_count/total:.1f}%)")
    
    # Breakdown by category
    print()
    print("Breakdown by category:")
    categories = {}
    for r in results:
        cat = r["test_id"].split("_")[0]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["passed"] == "True":
            categories[cat]["passed"] += 1
    
    for cat, stats in sorted(categories.items()):
        rate = 100 * stats["passed"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run evaluation on dataset")
    parser.add_argument("--dataset", default="/tmp/synthetic_dataset.csv", help="Input dataset CSV")
    parser.add_argument("--output", default="/tmp/eval_results.csv", help="Output results CSV")
    args = parser.parse_args()
    
    dataset = load_dataset(args.dataset)
    print(f"Loaded {len(dataset)} test cases from {args.dataset}")
    print()
    
    run_evaluation(dataset, args.output)
