"""Heuristics for classifying a question by legal domain and GK applicability."""

from __future__ import annotations

from dataclasses import dataclass, field


DOMAIN_RULES = {
    "civil": {
        "label": "Гражданское право",
        "gk_coverage": "yes",
        "triggers": [
            "договор",
            "сделк",
            "собственность",
            "собственник",
            "доверенн",
            "аренд",
            "займ",
            "кредит",
            "неустойк",
            "задат",
            "доля",
            "ооо",
            "наследств",
            "дарени",
            "купл",
            "продаж",
            "товар",
            "вещь",
            "недействител",
            "исков",
            "давност",
            "брак товара",
            "с браком",
        ],
    },
    "labor": {
        "label": "Трудовое право",
        "gk_coverage": "no",
        "triggers": ["работодатель", "зарплат", "отпуск", "увол", "трудов", "испытательн", "сотрудник"],
    },
    "criminal": {
        "label": "Уголовное право",
        "gk_coverage": "no",
        "triggers": ["уголов", "преступ", "мошенн", "краж", "убийств", "наркот", "угроза", "побои"],
    },
    "civil_procedure": {
        "label": "Гражданский процесс",
        "gk_coverage": "no",
        "triggers": ["иск", "подсуд", "суд", "повестк", "госпошлин", "заявлени", "апелляц"],
    },
    "administrative": {
        "label": "Административное право",
        "gk_coverage": "no",
        "triggers": ["штраф", "протокол", "коап", "административ", "лишение прав"],
    },
    "criminal_procedure": {
        "label": "Уголовный процесс",
        "gk_coverage": "no",
        "triggers": ["допрос", "обыск", "подозреваем", "обвиняем", "следоват", "адвокат", "полици"],
    },
    "consumer": {
        "label": "Защита прав потребителей",
        "gk_coverage": "partial",
        "triggers": [
            "потребител",
            "магазин",
            "гарант",
            "возврат",
            "некачествен",
            "услуг",
            "продавец",
            "моральн",
            "штраф 50",
            "товар ненадлежащего качества",
            "вещь с браком",
            "брак товара",
        ],
    },
    "housing": {
        "label": "Жилищное право",
        "gk_coverage": "partial",
        "triggers": ["жкх", "подъезд", "управляющ", "выселен", "квартир", "лифт", "сосед", "затоп"],
    },
    "family": {
        "label": "Семейное право",
        "gk_coverage": "no",
        "triggers": [
            "развод",
            "алименты",
            "ребенк",
            "супруг",
            "супруга",
            "муж",
            "жена",
            "отцовств",
            "семейн",
            "брачный договор",
            "зарегистрировать брак",
            "расторжение брака",
        ],
    },
    "tax": {
        "label": "Налоговое право",
        "gk_coverage": "no",
        "triggers": ["налог", "ндфл", "вычет", "декларац", "фнс", "пени по налогу"],
    },
    "land": {
        "label": "Земельное право",
        "gk_coverage": "partial",
        "triggers": ["земель", "участок", "межеван", "сервитут", "егрн", "кадастр"],
    },
    "corporate": {
        "label": "Корпоративное право",
        "gk_coverage": "partial",
        "triggers": ["акционер", "дивиденд", "совет директоров", "общее собрание акционеров", "ао", "эмисси"],
    },
}

GK_COVERAGE_PRIORITY = {"yes": 3, "partial": 2, "no": 1}
DOMAIN_PRIORITY = {
    "consumer": 5,
    "labor": 5,
    "criminal": 5,
    "criminal_procedure": 5,
    "administrative": 5,
    "civil_procedure": 5,
    "housing": 4,
    "family": 4,
    "tax": 4,
    "land": 4,
    "corporate": 4,
    "civil": 1,
}


@dataclass
class LegalDomainAssessment:
    primary_domain_id: str
    primary_domain_label: str
    gk_coverage: str
    can_answer_from_civil_code: bool
    confidence: float
    matched_domains: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def assess_legal_domain(question: str) -> LegalDomainAssessment:
    normalized = " ".join((question or "").lower().split())
    matches: list[tuple[str, int, list[str]]] = []

    for domain_id, rule in DOMAIN_RULES.items():
        matched_triggers = [trigger for trigger in rule["triggers"] if trigger in normalized]
        if matched_triggers:
            matches.append((domain_id, len(matched_triggers), matched_triggers))

    if _looks_like_defective_goods_question(normalized):
        matches = [item for item in matches if item[0] != "family"]
        consumer_match = next((item for item in matches if item[0] == "consumer"), None)
        if consumer_match is None:
            matches.append(("consumer", 2, ["вещь с браком", "дефект товара"]))

    if not matches:
        return LegalDomainAssessment(
            primary_domain_id="civil",
            primary_domain_label=DOMAIN_RULES["civil"]["label"],
            gk_coverage="yes",
            can_answer_from_civil_code=True,
            confidence=0.45,
            matched_domains=["civil"],
            reasoning=["fallback_to_civil_default"],
        )

    matches.sort(
        key=lambda item: (
            item[1],
            DOMAIN_PRIORITY.get(item[0], 1),
            GK_COVERAGE_PRIORITY[DOMAIN_RULES[item[0]]["gk_coverage"]],
        ),
        reverse=True,
    )

    primary_domain_id, trigger_count, matched_triggers = matches[0]
    primary_rule = DOMAIN_RULES[primary_domain_id]
    gk_coverage = primary_rule["gk_coverage"]
    confidence = min(0.95, 0.5 + trigger_count * 0.1)

    matched_domains = [domain_id for domain_id, _score, _triggers in matches]
    reasoning = [f"{primary_domain_id}: {', '.join(matched_triggers)}"]
    for domain_id, _score, triggers in matches[1:3]:
        reasoning.append(f"{domain_id}: {', '.join(triggers)}")

    return LegalDomainAssessment(
        primary_domain_id=primary_domain_id,
        primary_domain_label=primary_rule["label"],
        gk_coverage=gk_coverage,
        can_answer_from_civil_code=(gk_coverage != "no"),
        confidence=confidence,
        matched_domains=matched_domains,
        reasoning=reasoning,
    )


def _looks_like_defective_goods_question(normalized_question: str) -> bool:
    defective_goods_markers = (
        "вещь с браком",
        "товар с браком",
        "брак товара",
        "купил вещь с браком",
        "купил товар с браком",
        "ненадлежащего качества",
    )
    return any(marker in normalized_question for marker in defective_goods_markers)
