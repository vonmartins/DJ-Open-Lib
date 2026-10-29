"""Errors while enriching tracks."""


class EnrichError(Exception):
    """Enrichment cannot run: a missing tool, an unreachable service or a bad answer."""
