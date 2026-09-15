from sqlalchemy.ext.asyncio import AsyncSession

from app.services.brokerage.paper import PaperBrokerProvider
from app.services.brokerage.protocol import BrokerError, BrokerProvider

PROVIDERS = {"PAPER": PaperBrokerProvider}


def get_broker_provider(session: AsyncSession, provider_code: str) -> BrokerProvider:
    code = provider_code.strip().upper()
    factory = PROVIDERS.get(code)
    if factory is None:
        raise BrokerError(f"{code} is not a supported brokerage provider.")
    return factory(session)
