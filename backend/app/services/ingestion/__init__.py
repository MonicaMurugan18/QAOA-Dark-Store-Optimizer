"""Repeatable ingestion pipeline for real-world data.

Each module owns one source, validates it, and reports what it accepted and
what it rejected. Nothing is fabricated: a value that cannot be sourced is left
NULL or clearly labelled as an assumption.
"""
