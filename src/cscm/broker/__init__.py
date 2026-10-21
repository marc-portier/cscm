"""
CSCM Universal Data Access Layer (UDAL) Module.

Provides standard recurring dialogues and DataBroker abstraction to retrieve
hydrodynamic currents, tides, and environmental data across providers.
"""

from cscm.broker.base import AbstractDataBroker, NamedQuery, QueryResult
from cscm.broker.catalogue import (
    ColumnDefinition,
    ParamDefinition,
    QueryContract,
    QUERY_CATALOGUE,
    URI_QUERY_CURRENT,
    URI_QUERY_LANDMARK,
    URI_QUERY_MOONPHASE,
    URI_QUERY_TIDE,
    resolve_query_contract,
)
from cscm.broker.current import CmemsCurrentBroker
from cscm.broker.exceptions import (
    BrokerError,
    GeographicOutOfDomainError,
    InvalidQueryParameterError,
    OutOfDomainError,
    ProviderUnavailableError,
    TemporalOutOfDomainError,
)
from cscm.broker.local import (
    CompositeDataBroker,
    get_broker,
)
from cscm.broker.tide import (
    BelgianTideBroker,
    HicTideBroker,
    MdkTideBroker,
)

__all__ = [
    "AbstractDataBroker",
    "NamedQuery",
    "QueryResult",
    "CompositeDataBroker",
    "CmemsCurrentBroker",
    "BelgianTideBroker",
    "HicTideBroker",
    "MdkTideBroker",
    "get_broker",
    "QueryContract",
    "ParamDefinition",
    "ColumnDefinition",
    "QUERY_CATALOGUE",
    "URI_QUERY_CURRENT",
    "URI_QUERY_TIDE",
    "URI_QUERY_LANDMARK",
    "URI_QUERY_MOONPHASE",
    "resolve_query_contract",
    "BrokerError",
    "InvalidQueryParameterError",
    "OutOfDomainError",
    "GeographicOutOfDomainError",
    "TemporalOutOfDomainError",
    "ProviderUnavailableError",
]
