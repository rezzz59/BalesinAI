import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.db.engine import get_session
from app.db.models import ChatLog, TenantConfig
from app.graph.graph import get_compiled_graph
from app.graph.state import ChatState
from app.services.llm import get_safe_llm_client
from app.services.fonnte import FonnteGateway

logger = logging.getLogger(__name__)

async def auto_followup_loop():
    """Background task running every minute to find abandoned chats and send AI follow-ups."""
    while True:
        try:
            await asyncio.sleep(60)
            await _process_followups()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Followup loop error: {e}")

async def _process_followups():
    # Optimization: Do a raw SQL query or SQLAlchemy query to find the latest ChatLog per thread
    # Since sqlite doesn't support 'DISTINCT ON', we fetch recent unclosed chats and group manually.
    
    # We only care about chat logs from the last 24 hours to keep the scan light
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    with get_session() as session:
        recent_logs = session.query(ChatLog).filter(ChatLog.timestamp > cutoff).order_by(ChatLog.timestamp.asc()).all()
        
        # Group by thread_id to find the latest state of each conversation
        threads = {}
        for log in recent_logs:
            threads[log.thread_id] = log
            
        tenants_cache = {}
        
        for thread_id, latest_log in threads.items():
            # Only follow up if the conversation is still open, and the LAST message was from the bot (status='replied' or 'consultation')
            # Wait, our chat logs status are: 'replied', 'fallback', 'ordered', 'ghosting', 'unclear'
            # If the user just replied, status is what the bot did. If the user sent a message and we crashed, it's not replied.
            # If the bot already sent a follow up, how do we know? We can check if intent == 'auto_followup'.
            if latest_log.intent == "auto_followup" or latest_log.status in ("ordered", "fallback"):
                continue
                
            tenant_id = latest_log.tenant_id
            if tenant_id not in tenants_cache:
                tenant = session.get(TenantConfig, tenant_id)
                if not tenant:
                    tenants_cache[tenant_id] = None
                    continue
                import json
                try:
                    data = json.loads(tenant.onboarding_data or "{}")
                except Exception:
                    data = {}
                
                delay = data.get("followup_delay_minutes", 0)
                prompt = data.get("followup_prompt", "").strip()
                
                # Fetch WA config
                from app.services.crypto import decrypt_api_key
                from app.config import get_settings
                try:
                    token = decrypt_api_key(tenant.wa_api_key_encrypted, get_settings().encryption_key)
                except Exception:
                    token = ""
                    
                tenants_cache[tenant_id] = {
                    "delay": delay,
                    "prompt": prompt,
                    "token": token,
                    "sheet_id": tenant.google_sheet_id,
                    "data_source": tenant.data_source
                }
                
            tc = tenants_cache[tenant_id]
            if not tc or tc["delay"] <= 0 or not tc["prompt"] or not tc["token"]:
                continue
                
            # Has it been abandoned long enough?
            age_minutes = (datetime.now(timezone.utc) - latest_log.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60.0
            if age_minutes >= tc["delay"]:
                logger.info(f"Triggering auto follow-up for thread {thread_id} after {age_minutes:.1f} minutes")
                await _trigger_followup(latest_log, tc)
                
async def _trigger_followup(latest_log: ChatLog, tc: dict):
    """Trigger the LangGraph to compose and send a follow-up."""
    from app.services.bot_tester import _build_sheets_client
    
    # Send a synthetic state to the graph. We set the intent to 'auto_followup'
    # so the graph knows to just compose the message based on the merchant's prompt.
    state: ChatState = {
        "tenant_id": latest_log.tenant_id,
        "wa_number": latest_log.wa_number,
        "thread_id": latest_log.thread_id,
        "message_text": f"__SYSTEM_AUTO_FOLLOWUP__ {tc['prompt']}",
        "timestamp": datetime.now(timezone.utc),
        "intent": "auto_followup"
    }
    
    llm = get_safe_llm_client()
    sh = _build_sheets_client(latest_log.tenant_id)
    gateway = FonnteGateway(api_key=tc["token"])
    
    graph = get_compiled_graph(llm, sh, gateway)
    
    # We invoke async by running it in an executor because graph.invoke is blocking
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, graph.invoke, state)
