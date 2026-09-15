# Removed: this module was dead code.
#
# It defined an ``AISettings`` class with ``OPENAI_API_KEY`` that was never
# imported anywhere.  All AI configuration lives in ``app.core.config.Settings``
# (GROQ_API_KEY, AI_PROVIDER, etc.).
#
# Retained as an empty marker to avoid ``ImportError`` in case any third-party
# or migration code references this path.  Safe to delete entirely if no such
# references exist.
