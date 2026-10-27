"""Named errors of the domain."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the domain raises on purpose."""


class InvalidEventError(DomainError, ValueError):
    """An event is missing a field or has one that cannot be right."""


class InvalidCatalogEntryError(DomainError, ValueError):
    """A catalog entry breaks the golden-path contract (for example, its owner is a person, not a team)."""


class UnknownCommitError(DomainError, LookupError):
    """A trace asked for a commit that has no event."""
