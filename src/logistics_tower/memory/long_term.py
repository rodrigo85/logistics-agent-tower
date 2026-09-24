"""
Long-term semantic memory for the Logistics Control Tower.
Stores and retrieves persistent customer-specific constraints, loading dock rules,
and historical logistical idiosyncrasies across dispatch sessions in the SQL database.
"""

import logging
from typing import Any, Dict, List

from logistics_tower.db.repository import get_repository
from logistics_tower.db.seed import seed_database

logger = logging.getLogger(__name__)


class CustomerMemoryStore:
    """
    Persistent long-term memory for customer constraints, dock characteristics, and driver restrictions
    persisted directly in the relational database.
    """

    def __init__(self):
        seed_database()
        self.repo = get_repository()

    def add_rule(self, customer_name: str, rule_category: str, content: str, priority: str = "HIGH") -> None:
        self.repo.add_customer_rule(customer_name, rule_category, content, priority)
        logger.info(f"Memory: Persisted new rule for {customer_name} into SQL database.")

    def get_rules_for_customer(self, customer_name: str) -> List[Dict[str, Any]]:
        all_rules = self.repo.get_all_customer_rules()
        target = customer_name.strip().lower()
        return [r for r in all_rules if target in r["customer_name"].lower()]

    def search_rules(self, query: str) -> List[Dict[str, Any]]:
        tokens = query.lower().split()
        all_rules = self.repo.get_all_customer_rules()
        results = []
        for r in all_rules:
            text = f"{r['customer_name']} {r['rule_category']} {r['content']}".lower()
            if any(t in text for t in tokens):
                results.append(r)
        return results

    def get_all_rules(self) -> List[Dict[str, Any]]:
        return self.repo.get_all_customer_rules()


_instance = None


def get_customer_memory_store() -> CustomerMemoryStore:
    global _instance
    if _instance is None:
        _instance = CustomerMemoryStore()
    return _instance
