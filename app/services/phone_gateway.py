"""Abstract Phone Gateway interface for WhatsApp messaging."""
from abc import ABC, abstractmethod
from typing import Any
import asyncio
import random
import logging

logger = logging.getLogger(__name__)

class PhoneGatewayException(Exception):
    """Base exception for phone gateways."""


class PhoneGateway(ABC):
    """Abstract interface for WhatsApp phone gateways."""

    async def simulate_human_delay(self, message_text: str) -> None:
        """Simulate human typing delay to bypass Meta's anti-spam algorithm.
        
        The delay is calculated dynamically based on message length:
        - Base reaction time: 1.0 - 2.5 seconds
        - Typing speed: ~200 characters per minute (approx 3.3 chars per sec)
        - Max delay cap: 5 seconds (so users don't wait too long)
        """
        base_delay = random.uniform(1.0, 2.5)
        typing_delay = len(message_text) / 30.0 
        total_delay = min(5.0, base_delay + typing_delay)
        
        jitter = random.uniform(-0.5, 0.5)
        final_delay = max(0.5, total_delay + jitter)
        
        logger.info(f"Anti-Ban: Applying human delay of {final_delay:.2f}s for message length {len(message_text)}")
        await asyncio.sleep(final_delay)

    @abstractmethod
    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        """Send a WhatsApp message to the given phone number.

        Args:
            phone: Phone number in international format (e.g., +6281234567890)
            message: Message text to send

        Returns:
            Dict with API response details

        Raises:
            PhoneGatewayException: If sending fails after retries
        """
        pass
