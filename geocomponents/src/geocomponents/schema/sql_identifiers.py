"""Render psycopg identifiers to strings for offline SQL generation."""

from psycopg import sql

from geocomponents.descriptions.naming import validate_generated_name


def identifier(*parts: str) -> str:
    for part in parts:
        validate_generated_name(part)
    return sql.Identifier(*parts).as_string()


def qualified(name: str) -> str:
    """Split a plan's schema.object name before quoting each identifier."""
    schema, object_name = name.split(".", 1)
    return identifier(schema, object_name)
