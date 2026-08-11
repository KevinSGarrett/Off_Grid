class DomainError(Exception):
    """Base class for expected domain/application failures."""


class InvalidStateTransition(DomainError):
    """Requested lifecycle transition is not permitted by deterministic policy."""


class ExternalWriteBlocked(DomainError):
    """A requested external mutation was denied by server-side policy."""


class SourceFormatError(DomainError):
    """A source does not match a supported ingestion adapter."""


class ParserReconciliationError(DomainError):
    """Parsed section counts/content failed source reconciliation."""


class AmbiguousIdentityError(DomainError):
    """Identity candidates are ambiguous and must not be silently merged."""


class EvidenceGroundingError(DomainError):
    """An AI or derived claim references unsupported/nonexistent evidence."""


class IntegrationUnavailableError(DomainError):
    """An external dependency is temporarily unavailable."""
