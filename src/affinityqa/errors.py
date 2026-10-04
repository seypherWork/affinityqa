class AffinityQAError(Exception):
    """An expected failure with a safe, user-readable message."""


class SchemaError(AffinityQAError):
    pass


class ResolutionError(AffinityQAError):
    pass


class TransportError(AffinityQAError):
    pass


class BudgetError(AffinityQAError):
    pass

