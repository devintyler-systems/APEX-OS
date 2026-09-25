"""Bounded, read-only source discovery for the ApexOS in-season pipeline."""

from .source_probe import probe_sources, write_manifest

__all__ = ["probe_sources", "write_manifest"]
