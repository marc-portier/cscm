"""
Universal Data Access Layer (UDAL) - Core Broker Abstractions.

Defines QueryResult (with format negotiation), NamedQuery (query builder with provenance),
and AbstractDataBroker (dialogue interface).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import pandas as pd
import xarray as xr

from cscm.broker.catalogue import (
    QueryContract,
    resolve_query_contract,
)


@dataclass
class QueryResult:
    """
    Standardized payload returned by any UDAL broker query.
    Enforces format negotiation (pandas, xarray, records/dicts) alongside rich provenance metadata.
    """
    _df: pd.DataFrame
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convenience method returning data as a pandas DataFrame."""
        return self._df.copy()

    def to_xarray(self) -> xr.Dataset:
        """Convenience method returning data as an xarray Dataset indexed by timestamp."""
        df = self._df.copy()
        if "timestamp" in df.columns:
            return df.set_index("timestamp").to_xarray()
        return df.to_xarray()

    def to_records(self) -> List[Dict[str, Any]]:
        """Convenience method returning data as a list of row dictionaries."""
        return self._df.to_dict(orient="records")

    def to_dict(self) -> Dict[str, Any]:
        """Convenience method returning data as a column-oriented dictionary."""
        return self._df.to_dict()

    def data(self, as_format: str = "pandas") -> Any:
        """
        Dispatches tabular data converted to the negotiated format.
        
        Supported formats:
        - 'pandas' / 'dataframe' (default): returns a pandas DataFrame.
        - 'xarray' / 'dataset': returns an xarray Dataset indexed by timestamp.
        - 'records' / 'list': returns a list of row dictionaries.
        - 'dict': returns a dictionary mapping columns to value sequences.
        """
        fmt = as_format.strip().lower()
        format_handlers = {
            "pandas": self.to_dataframe,
            "df": self.to_dataframe,
            "dataframe": self.to_dataframe,
            "xarray": self.to_xarray,
            "xr": self.to_xarray,
            "dataset": self.to_xarray,
            "records": self.to_records,
            "list": self.to_records,
            "list[dict]": self.to_records,
            "dict": self.to_dict,
        }
        handler = format_handlers.get(fmt)
        if not handler:
            supported = ", ".join(sorted(set(["pandas", "xarray", "records", "dict"])))
            raise ValueError(
                f"Unsupported format '{as_format}'. Supported formats: {supported}"
            )
        return handler()

    def inspect(self) -> Dict[str, Any]:
        """Returns structured metadata inspection including row count, columns, and provenance."""
        uri = self.metadata.get("uri") or self.metadata.get("urn", "unknown")
        provider = self.metadata.get("provider", "unknown")
        return {
            "uri": uri,
            "provider": provider,
            "row_count": len(self._df),
            "columns": list(self._df.columns),
            "metadata": self.metadata,
        }

    def __len__(self) -> int:
        return len(self._df)

    def __repr__(self) -> str:
        uri = self.metadata.get("uri") or self.metadata.get("urn", "unknown")
        provider = self.metadata.get("provider", "unknown")
        return f"<QueryResult uri={uri!r} provider={provider!r} rows={len(self._df)}>"


@dataclass
class NamedQuery:
    """
    Fluent query builder instantiated via broker for a specific semantic URI.
    Maintains mandatory provenance trace to its generating broker.
    """
    uri: str
    contract: QueryContract
    broker: "AbstractDataBroker"
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def urn(self) -> str:
        """Alias for semantic URI."""
        return self.uri

    @property
    def supported_params(self) -> Dict[str, str]:
        """Dictionary of supported parameter names and descriptions."""
        return {name: p.description for name, p in self.contract.supported_params.items()}

    @property
    def result_schema(self) -> List[str]:
        """List of expected column names in the resulting dataset."""
        return list(self.contract.result_schema.keys())

    def param(self, key: str, value: Any) -> "NamedQuery":
        """Set a single query parameter with method chaining."""
        self.params[key] = value
        return self

    def params_dict(self, **kwargs) -> "NamedQuery":
        """Set multiple parameters at once with method chaining."""
        self.params.update(kwargs)
        return self

    # Aliases for fluent convenience
    set_param = param
    set_params = params_dict

    def execute(self, **kwargs) -> QueryResult:
        """Executes the query through the bound broker with optional inline parameter overrides."""
        if kwargs:
            self.params_dict(**kwargs)
        return self.broker.execute(self)

    def inspect(self) -> Dict[str, Any]:
        """Returns metadata regarding the broker, contract, supported params, and current values."""
        return {
            "uri": self.uri,
            "broker": self.broker.__class__.__name__,
            "contract": self.contract.inspect(),
            "current_params": self.params,
        }


# Fluent builder alias
QueryBuilder = NamedQuery


class AbstractDataBroker(ABC):
    """
    Abstract broker managing the dialogue for data retrieval across domains.
    Acts as a query factory (instantiating QueryBuilder / NamedQuery) and query executor.
    """

    @abstractmethod
    def named_query(self, uri: str) -> NamedQuery:
        """Instantiate a NamedQuery builder bound to this broker."""
        pass

    def build(self, uri: str) -> NamedQuery:
        """
        Fluent builder factory shortcut: instantiates a query builder bound to this broker.
        Example: broker.build('urn:cscm:query:tide').param('station', 'OST').execute()
        """
        return self.named_query(uri)

    @abstractmethod
    def _execute_query(self, query: NamedQuery) -> QueryResult:
        """Internal execution hook for a validated NamedQuery instance."""
        pass

    def execute(self, query_or_uri: Union[NamedQuery, str], **params) -> QueryResult:
        """
        Executes a query against this broker.
        Accepts either an existing NamedQuery object or a URI string with inline parameters.
        Example: broker.execute('urn:cscm:query:tide', station='OST')
        """
        if isinstance(query_or_uri, NamedQuery):
            if params:
                query_or_uri.params_dict(**params)
            return self._execute_query(query_or_uri)
        elif isinstance(query_or_uri, str):
            builder = self.build(query_or_uri)
            if params:
                builder.params_dict(**params)
            return self._execute_query(builder)
        else:
            raise TypeError(f"Expected NamedQuery or URI string, got {type(query_or_uri).__name__}")

    def query(self, uri: str, **params) -> QueryResult:
        """
        Convenience one-liner shortcut: instantiates a query and executes it immediately.
        Example: broker.query('urn:cscm:query:tide', station='OST')
        """
        return self.execute(uri, **params)