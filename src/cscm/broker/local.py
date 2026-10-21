"""
Universal Data Access Layer (UDAL) - Composite Local Data Broker.

Provides a unified facade/composite orchestrating domain-specific brokers
(CmemsCurrentBroker, HicTideBroker) using the Strategy/Composite pattern.
"""

import logging
from typing import Dict, Optional

from cscm.broker.base import AbstractDataBroker, NamedQuery, QueryResult
from cscm.broker.catalogue import (
    URI_QUERY_CURRENT,
    URI_QUERY_TIDE,
    resolve_query_contract,
)
from cscm.broker.current import CmemsCurrentBroker
from cscm.broker.tide import BelgianTideBroker, HicTideBroker, MdkTideBroker
from cscm.commons import singleton

log = logging.getLogger(__name__)


@singleton
class CompositeDataBroker(AbstractDataBroker):
    """
    Composite broker orchestrating domain brokers across semantic query URIs.
    Maintains a decoupled registry mapping URIs to specialized brokers.
    Decorated with @singleton to ensure a single shared orchestrator across application lifecycle.
    """

    def __init__(
        self,
        current_broker: Optional[CmemsCurrentBroker] = None,
        tide_broker: Optional[AbstractDataBroker] = None,
    ):
        self._registry: Dict[str, AbstractDataBroker] = {
            URI_QUERY_CURRENT: current_broker or CmemsCurrentBroker(),
            URI_QUERY_TIDE: tide_broker or BelgianTideBroker(),
        }

    def register_broker(self, uri: str, broker: AbstractDataBroker) -> None:
        """Dynamically register or override a domain broker for a semantic URI."""
        contract = resolve_query_contract(uri)
        self._registry[contract.uri] = broker

    def named_query(self, uri: str) -> NamedQuery:
        """Instantiate a NamedQuery builder bound to this broker."""
        contract = resolve_query_contract(uri)
        if contract.uri not in self._registry:
            known = ", ".join(self._registry.keys())
            raise NotImplementedError(
                f"No domain broker registered for query '{contract.uri}'. Registered brokers: {known}"
            )
        return NamedQuery(uri=contract.uri, contract=contract, broker=self)

    def _execute_query(self, query: NamedQuery) -> QueryResult:
        """Dispatches query execution to the registered domain broker."""
        contract = resolve_query_contract(query.uri)
        broker = self._registry.get(contract.uri)
        if broker is None:
            raise NotImplementedError(f"No broker registered for query '{contract.uri}'")
        return broker.execute(query)


def get_broker() -> CompositeDataBroker:
    """Returns the singleton instance of the CSCM composite local broker."""
    return CompositeDataBroker()