"""Framework adapters (spec/09): each returns the framework's native tool object.

Nothing here is imported by ``import sandboxio``; each module imports its framework on
first use and is installed by its own extra (``sandboxio[langgraph]``,
``sandboxio[openai-agents]``). Under 100 lines each; logic stays in core.
"""

from __future__ import annotations
