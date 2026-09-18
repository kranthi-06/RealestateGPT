"""RealEstateGPT worker infrastructure and worker implementations.

Workers live in the application package so they are importable, testable, and
callable both from CLI entry points (``backend/workers/*.py``) and from the
secret-protected scheduler API.
"""