# legal_copilot

`legal_copilot` — прототип юридического copilot-ассистента для вопросов, которые могут быть рассмотрены на основе Гражданского кодекса Российской Федерации.

Проект поддерживает:
- обработку одиночных юридических вопросов;
- инкрементальную обработку чанков транскрипции в режиме, близком к streaming;
- извлечение вопросов клиента из диалога;
- проверку того, можно ли отвечать на вопрос на основе корпуса ГК РФ;
- гибридный поиск статей с использованием GraphRAG;
- генерацию ответа с опорой на найденные статьи;
- fact check и проверку юридически значимых реплик юриста в транскрипте;
- batch-оценку на таблицах с вопросами;
- live demo-сайт для показа обработки транскрипций.

## Структура проекта

- [agents](./agents) — извлечение вопроса, определение правовой области, генерация ответа, fact check, проверка фраз юриста, рекомендации.
- [ingestion](./ingestion) — парсинг транскриптов, подготовка чанков, парсинг ГК РФ, генерация summary статей.
- [rag](./rag) — query understanding, query expansion, retrieval, reranking, графовая навигация по корпусу.
- [orchestration](./orchestration) — LangGraph pipeline, консольные demo, batch-скрипты, утилиты предрасчета.
- [api](./api) — lightweight backend для demo-сайта.
- [ui](./ui) — веб-интерфейс demo.
- [data](./data) — транскрипты, корпус ГК РФ, графовые индексы, кэшированные demo payloads.
- [config](./config) — локальные конфигурационные файлы для Yandex API.

## Установка

Из корня проекта:

```bash
pip install -r requirements.txt
```

Основные зависимости:
- `langgraph`
- `langchain-core`
- `openai`
- `pypdf`
- `sentence-transformers`

## Настройка Yandex

Для LLM-этапов проект читает конфигурацию из файлов:

- [config/yandex_api_key.txt](./config/yandex_api_key.txt)
- [config/yandex_folder_id.txt](./config/yandex_folder_id.txt)

Создать их можно на основе шаблонов:

- [config/yandex_api_key.txt.example](./config/yandex_api_key.txt.example)
- [config/yandex_folder_id.txt.example](./config/yandex_folder_id.txt.example)

При необходимости модель можно переопределить:

```powershell
$env:YANDEX_CLOUD_MODEL="gpt://<folder_id>/yandexgpt-lite/latest"
```

## Быстрый старт

### 1. Один вопрос через LangGraph

```bash
python -m legal_copilot.orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?"
```

Этот сценарий показывает:
- извлечение вопроса;
- routing;
- построение retrieval request;
- поиск статей;
- генерацию ответа;
- fact check;
- next actions.

### 2. Demo по транскрипции в консоли

```bash
python -m legal_copilot.orchestration.demo_langgraph --transcript legal_copilot/data/transcript_1.txt
```

Ограничить вывод первыми окнами:

```bash
python -m legal_copilot.orchestration.demo_langgraph --transcript legal_copilot/data/transcript_1.txt --limit 3
```

### 3. Пошаговый streaming demo

```bash
python -m legal_copilot.orchestration.demo_streaming_step_by_step --transcript legal_copilot/data/transcript_1.txt
```

### 4. Только поиск статей

```bash
python -m legal_copilot.orchestration.demo_graphrag --query "Какие корпоративные голоса нужны для продажи доли в ООО?" --top-k 5
```

## Live demo-сайт

Запуск backend:

```bash
python -m legal_copilot.api.server
```

Затем открыть:

```text
http://127.0.0.1:8000
```

Сайт поддерживает:
- выбор транскрипции;
- пошаговое проигрывание сценария;
- пользовательский и debug-режим;
- открытие текста статьи в модальном окне;
- подсветку реплик юриста, требующих внимания;
- логирование действий интерфейса в консоль браузера;
- логирование прогресса обработки сценария в консоль сервера.

## Предрасчет demo payloads

Live-сайт умеет использовать заранее сохраненные JSON payloads вместо полного пересчета сценария при каждом открытии transcript.

Предрасчет для всех доступных транскрипций:

```bash
python -m legal_copilot.orchestration.precompute_demo_payloads
```

Предрасчет только для одного transcript:

```bash
python -m legal_copilot.orchestration.precompute_demo_payloads --transcript transcript_1.txt
```

Принудительная пересборка, игнорируя кэш:

```bash
python -m legal_copilot.orchestration.precompute_demo_payloads --refresh
```

Кэшированные payloads сохраняются в:

- [data/demo_payloads](./data/demo_payloads)

API использует кэш автоматически, если он существует. Принудительно выполнить live-пересборку можно так:

```text
/api/demo?transcript=transcript_1.txt&refresh=1
```

## Подготовка корпуса

### Перегенерация summary статей

```bash
python -m legal_copilot.ingestion.article_summarizer --mode hybrid --overwrite
```

Только эвристический режим:

```bash
python -m legal_copilot.ingestion.article_summarizer --mode heuristic --overwrite
```

### Пересборка графа

```bash
python -m legal_copilot.rag.rebuild_graph
```

Типичный порядок обновления:
1. обновить `articles.json` или summary статей;
2. пересобрать `graph_index.json`;
3. снова запустить demo или batch.

## Основной pipeline

Основной pipeline в [orchestration/graph.py](./orchestration/graph.py) сейчас устроен так:

1. `ingest_chunk`
2. `extract_question`
3. `assess_legal_domain`
4. `retrieve`
5. `synthesize_answer`
6. `fact_check`
7. `suggest`

Основная точка входа из Python:

```python
from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.orchestration.graph import run_legal_copilot_turn

session = StreamingContextManager(session_id="demo")
result = run_legal_copilot_turn(
    "Нужно ли нотариальное удостоверение продажи доли в ООО?",
    context_manager=session,
    session_id="demo",
)

print(result.route)
print(result.answer_text)
```

## Batch-режим

Batch-скрипты:

- [orchestration/batch_answer_legal_questions.py](./orchestration/batch_answer_legal_questions.py)
- [orchestration/batch_answer_legal_questions_workbook.py](./orchestration/batch_answer_legal_questions_workbook.py)
- [orchestration/format_batch_answers.py](./orchestration/format_batch_answers.py)
- [orchestration/format_batch_answers_xlsx.py](./orchestration/format_batch_answers_xlsx.py)

Они используются для:
- прогона набора вопросов;
- сохранения референсных ответов и ответов модели;
- формирования отчетов в `.md` и `.xlsx`.

## Данные

Ключевые файлы корпуса:

- [data/civil_code/articles.json](./data/civil_code/articles.json)
- [data/civil_code/graph_index.json](./data/civil_code/graph_index.json)

Файлы транскрипций:

- [data/transcript_1.txt](./data/transcript_1.txt)
- [data/transcript_2.txt](./data/transcript_2.txt)
- [data/transcript_3.txt](./data/transcript_3.txt)
- [data/transcript_4.txt](./data/transcript_4.txt)
- [data/transcript_5.txt](./data/transcript_5.txt)
- [data/transcript_6.txt](./data/transcript_6.txt)

## Ограничения

- Проект в первую очередь ориентирован на сценарии по ГК РФ.
- Вопросы из других отраслей права могут требовать иных кодексов и специальных законов.
- Качество ответа зависит от того, насколько хорошо вопрос покрывается текущим корпусом `articles.json`.
- Полный live-прогон длинных транскриптов может быть медленным без заранее подготовленного кэша.

## Полезные команды

Проверка одного вопроса:

```bash
python -m legal_copilot.orchestration.demo_question_langgraph --query "Купил вещь с браком — что могу требовать?"
```

Проверка retrieval без полного ответа:

```bash
python -m legal_copilot.orchestration.demo_graphrag --query "Купил вещь с браком — что могу требовать?" --top-k 5
```

Пошаговый прогон транскрипции в консоли:

```bash
python -m legal_copilot.orchestration.demo_streaming_step_by_step --transcript legal_copilot/data/transcript_1.txt --limit 3
```

Пересборка графа:

```bash
python -m legal_copilot.rag.rebuild_graph
```
