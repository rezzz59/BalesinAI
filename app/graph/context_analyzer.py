"""Context analyzer node for mapping customer descriptions to policy conditions."""
import json
import logging
from typing import Any

from app.graph.state import ChatState
from app.services.llm import LLMError

logger = logging.getLogger(__name__)


def analyze_customer_context(state: ChatState, llm_client: Any) -> dict:
    """Map customer description to policy/product conditions via LLM reasoning.

    Retrieves catalog_answer or product_match, combines with policy info from sheets,
    then uses LLM to map customer message to structured context data including
    mapped_conditions, issue_type, primary_intent, confidence, and reasoning.

    Returns a dict update that gets merged into state under "customer_context".
    """
    retrieved_rows = state.get('catalog_answer') or state.get('product_match') or []

    # Build context prompt with policy info from sheets
    policy_info = ""
    if state.get('policy_sheet_rows'):
        for row in state['policy_sheet_rows']:
            policy_info += f"\n{row['rule_key']}: {row['description']}"

    # Format retrieved rows nicely
    retrieved_text = ""
    if retrieved_rows:
        if isinstance(retrieved_rows, list):
            for item in retrieved_rows[:5]:  # Limit to first 5 to avoid overflow
                if isinstance(item, dict):
                    retrieved_text += f"- {item}"
                else:
                    retrieved_text += f"- {str(item)}"
        elif isinstance(retrieved_rows, str):
            retrieved_text = retrieved_rows
        else:
            retrieved_text = str(retrieved_rows)

    prompt = f"""Anda adalah analis konteks pesanan. Tugaskan: pemetasikan deskripsi pelanggan ke kondisi-kondisi dalam data yang diberikan.

PESAN PELANGGAN: {state['message_text']}

DATA RELEVAN:
Faq/Produk: {retrieved_text}
Kebijakan: {policy_info}

TUGAS:
1. Kondisi/kriteria apa saja dari data yang DIPENUHI oleh situasi pelanggan ini? (list string)
2. Apa jenis issue/keluhan jika ada? (misal: product_damage, wrong_size, delivery_delay, none)
3. Apa intent utama? (faq, check_product, confirm_order, complaint, return_request)
4. Berapa tingkat keyakinan mapping ini? (skor 0.0-1.0)
5. Mengapa Anda melakukan pemetaan ini? (justifikasi singkat 1-2 kalimat)

FORMAT HARUS JSON TIDAK ADA teks pendahuluan atau penutup:
{{
  "mapped_conditions": [],
  "issue_type": "",
  "primary_intent": "",
  "confidence": 0.0,
  "reasoning": ""
}}
"""

    try:
        # Pass full conversation history so LLM can leverage multi-turn context
        messages = state.get("messages") or []
        result = llm_client.classify_with_history(messages + [{"role": "user", "content": prompt}])

        # Parse JSON output
        if isinstance(result, dict):
            mapping = json.loads(result.get("text", "{}"))
        else:
            mapping = {}

        # Return default if empty or missing required fields
        if not mapping or not all(k in mapping for k in ["mapped_conditions", "issue_type", "primary_intent", "confidence", "reasoning"]):
            mapping = {
                "mapped_conditions": [],
                "issue_type": "none",
                "primary_intent": state.get("intent", "unclear"),
                "confidence": 0.5,
                "reasoning": "No clear mapping detected or response format invalid"
            }

        # Wrap in customer_context dict so it merges as a single nested field into ChatState
        return {"customer_context": mapping}

    except (LLMError, json.JSONDecodeError) as e:
        logger.error("context_analysis_failed", extra={"error": str(e), "tenant_id": state.get("tenant_id", "")})
        mapping = {
            "mapped_conditions": [],
            "issue_type": "none",
            "primary_intent": state.get("intent", "unclear"),
            "confidence": 0.3,
            "reasoning": "Analysis failed"
        }
        return {"customer_context": mapping}
    except Exception as e:
        logger.error("context_analysis_failed", extra={"error": str(e), "tenant_id": state.get("tenant_id", "")})
        mapping = {
            "mapped_conditions": [],
            "issue_type": "none",
            "primary_intent": state.get("intent", "unclear"),
            "confidence": 0.3,
            "reasoning": "Unexpected error during analysis"
        }
        return {"customer_context": mapping}