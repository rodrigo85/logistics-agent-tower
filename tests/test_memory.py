"""Unit tests for CustomerMemoryStore long-term memory backed by SQL database."""

from logistics_tower.memory.long_term import CustomerMemoryStore


def test_customer_memory_store_retrieval():
    store = CustomerMemoryStore()

    store.add_rule(
        customer_name="Supermercado Bistek - Fazenda",
        rule_category="ACCESS_RESTRICTION",
        content="Rampa estreita, apenas VUC permitido na doca.",
        priority="CRITICAL",
    )

    rules = store.get_rules_for_customer("Bistek")
    assert len(rules) >= 1
    assert any("VUC" in r["content"] for r in rules)

    all_rules = store.get_all_rules()
    assert len(all_rules) >= 1
