"""Errors raised by the canonical model."""


class ValidationError(ValueError):
    """A model value violates one of its invariants."""

    def __init__(self, entity: str, field: str, message: str) -> None:
        super().__init__(f"{entity}.{field}: {message}")
        self.entity = entity
        self.field = field
        self.message = message
