"""
ChromaDBStore: Utility for storing and searching applicant/role embeddings using ChromaDB.
"""
from chromadb import Client
from chromadb.config import Settings
from pathlib import Path
from typing import Any, Dict, List
from config.settings import AppConfig
from utils.logger import AppLogger
import os

class ChromaDBStore:
    """Manages ChromaDB vector database for applicants and roles."""
    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger
        db_path = os.getenv("CHROMADB_PATH", str(config.data_path / "chromadb"))
        self.client = Client(Settings(persist_directory=db_path))
        self.applicants_collection = self.client.get_or_create_collection("applicants")
        self.roles_collection = self.client.get_or_create_collection("roles")

    def add_embedding(self, collection: str, id: str, embedding: List[float], metadata: Dict[str, Any]) -> None:
        col = self._get_collection(collection)
        col.add(ids=[id], embeddings=[embedding], metadatas=[metadata])
        self.logger.log_kv("CHROMADB_ADD", collection=collection, id=id)

    def query_embedding(self, collection: str, embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        col = self._get_collection(collection)
        results = col.query(query_embeddings=[embedding], n_results=top_k)
        self.logger.log_kv("CHROMADB_QUERY", collection=collection, top_k=top_k)
        return results.get("metadatas", [])

    def _get_collection(self, collection: str):
        if collection == "applicants":
            return self.applicants_collection
        elif collection == "roles":
            return self.roles_collection
        else:
            raise ValueError(f"Unknown collection: {collection}")
