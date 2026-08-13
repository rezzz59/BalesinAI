print("Cekat AI Chatbot Architecture:")
print("- They heavily leverage the official WhatsApp Business API.")
print("- They use LLM AI Agents (likely fine-tuned or prompt-engineered, handling local dialects/typos) rather than keyword-based state machines.")
print("- They have a Drag-and-Drop Visual Flow Designer for structured operations (like booking or promos), which suggests an agentic routing / state machine hybrid approach.")

print("\nProduct Search and FAQ:")
print("- The AI is trained by pasting SOPs, catalogs, prices, and policies into a 'Knowledge Base' (this strongly implies RAG - Retrieval-Augmented Generation using embeddings and vector search).")
print("- It takes ~5 minutes to index the knowledge base, pointing to automated chunking and embedding pipelines.")

print("\nMaintaining Context and Tone:")
print("- The AI doesn't just match keywords; it understands intent (NLU/NLP).")
print("- It maintains context across the chat (e.g., handles follow-up questions well, remembering earlier parts of the thread).")
print("- Handles 'bahasa campur' (mixed languages) and 'singkatan' (abbreviations) naturally.")
print("- Built-in human handoff (auto-escalation): If the AI gets stuck, it transfers to a human agent along with the full chat context and private notes.")

print("\nOrder Flows vs Open-ended FAQs:")
print("- Open FAQs are handled via the RAG knowledge base.")
print("- Order flows (cek ongkir/shipping rates, QR payments) are integrated directly in the chat using API integrations.")
print("- The system is capable of extracting order details (items, quantity, address, contact) from natural conversation to automatically construct a complete order, showing advanced Named Entity Recognition (NER) or function-calling/tool-use by the LLM.")
