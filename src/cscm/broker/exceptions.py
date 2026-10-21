"""
Universal Data Access Layer (UDAL) - Broker Exceptions.

Establishes a structured exception hierarchy for semantic query validation,
domain boundary enforcement (geographic and temporal), and provider errors.
"""


class BrokerError(Exception):
    """Base exception for all Universal Data Access Layer (UDAL) broker errors."""
    pass


class InvalidQueryParameterError(BrokerError):
    """Raised when query parameters are missing, malformed, or contradictory (e.g. end_time < start_time)."""
    pass


class OutOfDomainError(BrokerError):
    """Base exception raised when a query asks for data outside a provider's operational domain."""
    pass


class GeographicOutOfDomainError(OutOfDomainError):
    """
    Raised when requested spatial coordinates or station are outside the geographic boundaries
    of the provider (e.g., asking Belgian coastal tide models for coordinates in Paris or the Mediterranean).
    """
    def __init__(self, lat: float, lon: float, provider: str, max_distance_km: float = 35.0):
        self.lat = lat
        self.lon = lon
        self.provider = provider
        self.max_distance_km = max_distance_km
        super().__init__(
            f"Coordinates ({lat:.4f}, {lon:.4f}) are outside the {provider} operational domain "
            f"(exceeds {max_distance_km} km from the Belgian coastline)."
        )


class TemporalOutOfDomainError(OutOfDomainError):
    """
    Raised when requested time interval is outside the temporal capability of the provider
    (e.g., asking an observation-only sensor provider for future dates, or asking a forecast
    model beyond its operational lookahead horizon).
    """
    pass


class ProviderUnavailableError(BrokerError):
    """Raised when an upstream data provider is unreachable and no local cached data is available."""
    pass