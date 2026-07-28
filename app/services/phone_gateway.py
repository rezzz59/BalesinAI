"""Abstract Phone Gateway interface for WhatsApp messaging."""
from abc import ABC, abstractmethod
from typing import Any


class PhoneGatewayException(Exception):
    """Base exception for phone gateways."""


class PhoneGateway(ABC):
    """Abstract interface for WhatsApp phone gateways."""

    @abstractmethod
    def send_message(self, phone: str, message: str) -> dict[str, Any]:
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
