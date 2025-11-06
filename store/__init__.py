"""Store package: Weaviate plumbing and domain facades.

Exports:
- WeaviateStore: central client + schema plumbing
- CVStore, RoleStore: domain facades
"""
from .weaviate_store import WeaviateStore  # noqa: F401
from .cv_store import CVStore  # noqa: F401
from .role_store import RoleStore  # noqa: F401
