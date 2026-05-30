"""Query expansion for legal-domain retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_copilot.agents.query_expansion_agent import (
    LLMExpansionResult,
    expand_query_with_llm,
)
from legal_copilot.rag.embeddings import normalize_text

LEGAL_EXPANSION_RULES = {
    "notary": {
        "triggers": ["нотари", "удостовер", "нотариальн"],
        "terms": ["нотариальная форма", "нотариальное удостоверение сделки", "удостоверение сделки нотариусом"],
    },
    "share_transfer": {
        "triggers": ["доля", "ооо", "участник", "продаж", "отчуждени"],
        "terms": ["отчуждение доли", "продажа доли третьему лицу", "переход доли", "участник общества"],
    },
    "registration": {
        "triggers": ["егрюл", "реестр", "регистрац", "запись"],
        "terms": ["государственная регистрация", "внесение записи в реестр", "момент перехода права"],
    },
    "invalidity": {
        "triggers": ["недействитель", "ничтожн", "оспорим", "сделк"],
        "terms": ["недействительность сделки", "ничтожная сделка", "оспоримая сделка", "последствия недействительности"],
    },
    "limitation": {
        "triggers": ["исков", "давност", "срок"],
        "terms": ["срок исковой давности", "течение срока исковой давности", "специальные сроки исковой давности"],
    },
    "corporate_approval": {
        "triggers": ["собрани", "голос", "одобрени", "кворум", "решение"],
        "terms": ["решение общего собрания", "корпоративное одобрение", "кворум и большинство голосов"],
    },
    "creditor_risk": {
        "triggers": ["кредитор", "досроч", "обязательств", "должник", "ковенант"],
        "terms": ["права кредитора", "досрочное исполнение обязательства", "перемена лиц в обязательстве"],
    },
    "damages": {
        "triggers": ["убыт", "вред", "возмещен"],
        "terms": ["возмещение убытков", "причинение вреда", "компенсация ущерба"],
    },
}


@dataclass
class ExpandedQuery:
    original_query: str
    expanded_query: str
    added_terms: list[str] = field(default_factory=list)
    triggered_rules: list[str] = field(default_factory=list)
    llm_result: LLMExpansionResult | None = None


def expand_legal_query(query: str) -> ExpandedQuery:
    normalized_query = normalize_text(query)
    added_terms: list[str] = []
    triggered_rules: list[str] = []

    for rule_name, rule in LEGAL_EXPANSION_RULES.items():
        if any(trigger in normalized_query for trigger in rule["triggers"]):
            triggered_rules.append(rule_name)
            for term in rule["terms"]:
                if normalize_text(term) not in normalized_query and term not in added_terms:
                    added_terms.append(term)

    llm_result = expand_query_with_llm(query)
    if llm_result.keywords:
        for term in llm_result.keywords:
            if normalize_text(term) not in normalized_query and term not in added_terms:
                added_terms.append(term)

    if not added_terms:
        return ExpandedQuery(
            original_query=query,
            expanded_query=query,
            added_terms=[],
            triggered_rules=[],
            llm_result=llm_result,
        )

    expanded_query = f"{query}\n\nЮридически связанные термины: " + "; ".join(added_terms)
    return ExpandedQuery(
        original_query=query,
        expanded_query=expanded_query,
        added_terms=added_terms,
        triggered_rules=triggered_rules,
        llm_result=llm_result,
    )
