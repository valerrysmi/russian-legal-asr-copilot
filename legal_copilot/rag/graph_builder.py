"""Build a lightweight legal knowledge graph over Civil Code articles."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from legal_copilot.rag.embeddings import normalize_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "data" / "civil_code" / "articles.json"
DEFAULT_GRAPH_PATH = PROJECT_ROOT / "data" / "civil_code" / "graph_index.json"
ARTICLE_REFERENCE_RE = re.compile(
    r"\bст(?:атья|атьи|атье|атью|\.?)\s+(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
REPEALED_ARTICLE_RE = re.compile(r"\bутрат\w*\s+сил", re.IGNORECASE)

CONCEPT_PATTERNS = {
    "legal_capacity": ("правоспособность", ["правоспособн", "дееспособн", "гражданин", "физическ"]),
    "legal_entity": ("юридическое лицо", ["юридическ", "организац", "устав", "учредител"]),
    "representation": ("представительство", ["представител", "доверенност", "полномоч"]),
    "power_of_attorney": ("доверенность", ["доверенност", "передовер", "полномоч"]),
    "agency": ("поручение", ["поручени", "поверен", "доверител"]),
    "property_rights": ("вещные права", ["вещн", "имущество", "собственник", "владени"]),
    "possession": ("владение", ["владени", "добросовестн", "незаконн", "истребован"]),
    "acquisition": ("приобретение права", ["приобретен", "возникновен", "основани", "переход"]),
    "termination": ("прекращение права", ["прекращен", "утрат", "отказ", "ликвидац"]),
    "inheritance": ("наследование", ["наслед", "завещан", "наследник", "наследодател"]),
    "will": ("завещание", ["завещан", "завещател", "нотари", "наследник"]),
    "lease": ("аренда", ["аренд", "нанимател", "арендатор", "арендодател"]),
    "rent": ("наем жилого помещения", ["наем", "жил", "нанимател", "помещен"]),
    "sale": ("купля-продажа", ["купл", "продаж", "товар", "покупател", "продавец"]),
    "supply": ("поставка", ["поставк", "поставщик", "покупател", "товар"]),
    "donation": ("дарение", ["дарени", "дарител", "одаряем", "безвозмезд"]),
    "loan": ("заем", ["заем", "заимодав", "заемщик", "возврат"]),
    "credit": ("кредит", ["кредит", "банк", "заемщик", "процент"]),
    "bank_account": ("банковский счет", ["счет", "банк", "клиент", "расчет"]),
    "insurance": ("страхование", ["страхован", "страховщик", "страхователь", "страхов"]),
    "pledge": ("залог", ["залог", "залогодержател", "залогодател", "обеспечени"]),
    "surety": ("поручительство", ["поручител", "кредитор", "должник", "ответствен"]),
    "guarantee": ("независимая гарантия", ["гарант", "гаранти", "бенефициар", "принципал"]),
    "penalty": ("неустойка", ["неустойк", "штраф", "пен", "ответствен"]),
    "liability": ("гражданско-правовая ответственность", ["ответствен", "нарушени", "обязательств", "вина"]),
    "obligation": ("обязательство", ["обязательств", "должник", "кредитор", "исполнени"]),
    "performance": ("исполнение обязательства", ["исполнени", "надлежащ", "должник", "кредитор"]),
    "default": ("просрочка", ["просрочк", "срок", "неисполнени", "задержк"]),
    "termination_contract": ("расторжение договора", ["расторжен", "отказ", "прекращен", "договор"]),
    "assignment": ("уступка требования", ["уступк", "цесс", "требован", "кредитор"]),
    "debt_transfer": ("перевод долга", ["перевод", "долг", "должник", "согласие"]),
    "setoff": ("зачет", ["зачет", "встречн", "однородн", "требован"]),
    "novation": ("новация", ["новац", "замен", "обязательств"]),
    "unjust_enrichment": ("неосновательное обогащение", ["неосновательн", "обогащен", "приобретен", "сбережен"]),
    "tort": ("деликт", ["причинен", "вред", "ответствен", "источник повышенной опасности"]),
    "moral_damage": ("компенсация морального вреда", ["моральн", "вред", "компенсац"]),
    "intellectual_property": ("интеллектуальная собственность", ["интеллектуальн", "исключительн", "авторск", "патент"]),
    "exclusive_right": ("исключительное право", ["исключительн", "правообладател", "использован"]),
    "license": ("лицензионный договор", ["лицензи", "лицензиар", "лицензиат", "использован"]),
    "copyright": ("авторское право", ["автор", "произведен", "обнародован", "исключительн"]),
    "patent": ("патентное право", ["патент", "изобретен", "полезн", "промышленн"]),
    "commercial_secret": ("коммерческая тайна", ["коммерческ", "тайн", "секрет производств", "ноу-хау"]),
    "good_faith": ("добросовестность", ["добросовестн", "разумн", "справедлив"]),
    "abuse_of_right": ("злоупотребление правом", ["злоупотреблен", "недобросовестн", "обход закона"]),
    "public_order": ("публичный порядок", ["публичн", "основы правопорядк", "нравствен"]),
    "consumer": ("потребитель", ["потребител", "исполнител", "услуг", "заказчик"]),
    "services": ("оказание услуг", ["услуг", "исполнител", "заказчик", "возмездн"]),
    "work_contract": ("подряд", ["подряд", "подрядчик", "заказчик", "результат работ"]),
    "transport": ("перевозка", ["перевозк", "перевозчик", "груз", "пассажир"]),
    "storage": ("хранение", ["хранени", "хранител", "поклажедател", "вещ"]),
    "commission": ("комиссия", ["комисс", "комиссионер", "комитент", "сделк"]),
    "commercial_concession": ("коммерческая концессия", ["концесс", "правообладател", "пользователь", "коммерческ"]),
    "partnership": ("простое товарищество", ["товариществ", "совместн", "вклад", "прибыль"]),
    "corporation": ("корпорация", ["корпоративн", "участник", "членств", "управлен"]),
    "reorganization": ("реорганизация", ["реорганизац", "слиян", "присоединен", "разделен", "выделен", "преобразован"]),
    "liquidation": ("ликвидация", ["ликвидац", "ликвидационн", "прекращен", "кредитор"]),
    "bankruptcy_signal": ("банкротство", ["банкрот", "несостоятельн", "конкурсн", "наблюден"]),
    "securities": ("ценные бумаги", ["ценн", "бумаг", "акци", "облигац", "вексел"]),
    "shareholder_rights": ("права акционера", ["акционер", "акци", "дивиденд", "голосован"]),
    "llc_participant": ("права участника ООО", ["участник", "общество", "доля", "уставн"]),
    "preemptive_right": ("преимущественное право", ["преимуществен", "покупк", "доля", "акци"]),
    "major_transaction": ("крупная сделка", ["крупн", "сделк", "одобрен", "стоимост"]),
    "interested_party_transaction": ("сделка с заинтересованностью", ["заинтересован", "сделк", "одобрен", "аффилирован"]),
    "state_property": ("государственная собственность", ["государственн", "муниципальн", "собственност"]),
    "real_estate": ("недвижимость", ["недвижим", "земельн", "здани", "сооружен", "помещен"]),
    "land": ("земельный участок", ["земельн", "участок", "кадастр", "границ"]),
    "servitude": ("сервитут", ["сервитут", "ограниченн", "пользован", "участок"]),
    "mortgage": ("ипотека", ["ипотек", "залог недвижим", "закладн"]),
    "registration_rights": ("регистрация прав", ["регистрац", "прав", "недвижим", "реестр", "егрн"]),
    "limitation_period_start": ("начало течения исковой давности", ["узнал", "должен был узнать", "нарушени", "давност"]),
    "restoration": ("восстановление нарушенного права", ["восстановлен", "защит", "нарушенн", "прав"]),
    "specific_performance": ("понуждение к исполнению", ["понужден", "исполнени", "натур", "обязательств"]),
}


@dataclass
class GraphConnection:
    target: str
    edge_type: str
    weight: float = 1.0


@dataclass
class GraphIndex:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    adjacency: dict[str, list[GraphConnection]] = field(default_factory=dict)

    def add_node(self, node_id: str, **attributes: Any) -> None:
        node = self.nodes.setdefault(node_id, {})
        node.update(attributes)
        self.adjacency.setdefault(node_id, [])

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        reverse_edge_type: str | None = None,
    ) -> None:
        self._append_connection(source, target, edge_type, weight)
        self._append_connection(target, source, reverse_edge_type or edge_type, weight)

    def neighbors(self, node_id: str) -> list[GraphConnection]:
        return self.adjacency.get(node_id, [])

    def _append_connection(
        self,
        source: str,
        target: str,
        edge_type: str,
        weight: float,
    ) -> None:
        connections = self.adjacency.setdefault(source, [])
        for connection in connections:
            if (
                connection.target == target
                and connection.edge_type == edge_type
                and connection.weight == weight
            ):
                return
        connections.append(GraphConnection(target=target, edge_type=edge_type, weight=weight))

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": self.nodes,
            "adjacency": {
                node_id: [
                    {
                        "target": connection.target,
                        "edge_type": connection.edge_type,
                        "weight": connection.weight,
                    }
                    for connection in connections
                ]
                for node_id, connections in self.adjacency.items()
            },
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "GraphIndex":
        payload = json.loads(path.read_text(encoding="utf-8"))
        index = cls(nodes=payload["nodes"], adjacency={})
        for node_id, connections in payload["adjacency"].items():
            index.adjacency[node_id] = [
                GraphConnection(
                    target=connection["target"],
                    edge_type=connection["edge_type"],
                    weight=connection.get("weight", 1.0),
                )
                for connection in connections
            ]
        return index


def _structure_node_id(prefix: str, value: str) -> str:
    return f"{prefix}:{normalize_text(value)}"


def _article_node_id(article_number: str) -> str:
    return f"article:{article_number}"


def _keyword_node_id(keyword: str) -> str:
    return f"keyword:{normalize_text(keyword)}"


def _extract_article_references(text: str) -> set[str]:
    return {match.group(1) for match in ARTICLE_REFERENCE_RE.finditer(text)}


def _extract_concepts(text: str) -> list[tuple[str, str]]:
    normalized = normalize_text(text)
    found = []
    for concept_key, (label, stems) in CONCEPT_PATTERNS.items():
        if any(stem in normalized for stem in stems):
            found.append((concept_key, label))
    return found


def _clean_keywords(raw_keywords: Any) -> list[str]:
    if not isinstance(raw_keywords, list):
        return []
    keywords = []
    seen: set[str] = set()
    for keyword in raw_keywords:
        if not isinstance(keyword, str):
            continue
        cleaned = keyword.strip()
        normalized = normalize_text(cleaned)
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(cleaned)
    return keywords


def _is_repealed_article(article: dict[str, Any]) -> bool:
    title = str(article.get("title", ""))
    summary = str(article.get("summary", ""))
    text = str(article.get("text", ""))
    searchable = f"{title}\n{summary}\n{text[:400]}"
    return bool(REPEALED_ARTICLE_RE.search(searchable))


def build_graph_from_articles(articles: list[dict[str, Any]]) -> GraphIndex:
    graph = GraphIndex()
    active_articles = [article for article in articles if not _is_repealed_article(article)]

    for article in active_articles:
        article_number = str(article["article_number"])
        article_node_id = _article_node_id(article_number)
        graph.add_node(
            article_node_id,
            node_type="article",
            article_number=article_number,
            title=article["title"],
            summary=article.get("summary", ""),
            keywords=_clean_keywords(article.get("keywords")),
            chapter=article.get("chapter"),
            section=article.get("section"),
            subsection=article.get("subsection"),
            part=article.get("part"),
        )

        structure_chain = [
            ("part", article.get("part")),
            ("section", article.get("section")),
            ("subsection", article.get("subsection")),
            ("chapter", article.get("chapter")),
        ]
        previous_structure_node = None
        for prefix, value in structure_chain:
            if not value:
                continue
            structure_node_id = _structure_node_id(prefix, value)
            graph.add_node(structure_node_id, node_type=prefix, label=value)
            if previous_structure_node and structure_node_id != previous_structure_node:
                graph.add_edge(
                    previous_structure_node,
                    structure_node_id,
                    "contains",
                    reverse_edge_type="part_of",
                )
            previous_structure_node = structure_node_id

        if previous_structure_node:
            graph.add_edge(
                article_node_id,
                previous_structure_node,
                "part_of",
                reverse_edge_type="contains",
            )

        concept_source = " ".join(
            [
                article.get("title", ""),
                article.get("summary", ""),
                " ".join(_clean_keywords(article.get("keywords"))),
                article.get("text", ""),
            ]
        )
        for concept_key, concept_label in _extract_concepts(concept_source):
            concept_node_id = f"concept:{concept_key}"
            graph.add_node(concept_node_id, node_type="concept", label=concept_label)
            graph.add_edge(
                article_node_id,
                concept_node_id,
                "mentions_concept",
                weight=0.7,
                reverse_edge_type="concept_in_article",
            )

        for keyword in _clean_keywords(article.get("keywords")):
            keyword_node_id = _keyword_node_id(keyword)
            graph.add_node(keyword_node_id, node_type="keyword", label=keyword)
            graph.add_edge(
                article_node_id,
                keyword_node_id,
                "mentions_keyword",
                weight=0.78,
                reverse_edge_type="keyword_in_article",
            )

    article_numbers = {str(article["article_number"]) for article in active_articles}
    for article in active_articles:
        article_number = str(article["article_number"])
        source_node_id = _article_node_id(article_number)
        references = _extract_article_references(
            f"{article.get('summary', '')} {article.get('text', '')}"
        )
        for reference in references:
            if reference not in article_numbers or reference == article_number:
                continue
            graph.add_edge(
                source_node_id,
                _article_node_id(reference),
                "refers_to",
                weight=0.9,
                reverse_edge_type="referenced_by",
            )

    return graph


def build_and_save_graph(
    article_path: Path = DEFAULT_ARTICLE_PATH,
    output_path: Path = DEFAULT_GRAPH_PATH,
) -> GraphIndex:
    articles = json.loads(article_path.read_text(encoding="utf-8"))
    graph = build_graph_from_articles(articles)
    graph.save(output_path)
    return graph
