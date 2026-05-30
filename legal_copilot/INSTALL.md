# Установка и запуск `legal_copilot`

Этот файл содержит отдельную подробную инструкцию по установке, настройке и запуску проекта `legal_copilot`.

## TL;DR

Если нужен максимально короткий сценарий первого запуска:

```powershell
git clone https://github.com/valerrysmi/legal_copilot
cd legal_copilot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install langgraph langchain-core openai pypdf sentence-transformers
Copy-Item config\yandex_api_key.txt.example config\yandex_api_key.txt
Copy-Item config\yandex_folder_id.txt.example config\yandex_folder_id.txt
python -m orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?"
```

После этого можно запускать веб-демо:

```powershell
python -m api.server
```

И открыть:

```text
http://127.0.0.1:8000
```

## 1. Что это за проект

`legal_copilot` — это прототип юридического copilot-ассистента для вопросов, которые могут быть рассмотрены на основе Гражданского кодекса Российской Федерации.

Проект поддерживает:

- обработку одиночных юридических вопросов;
- обработку транскриптов консультационного диалога;
- извлечение вопроса клиента из диалога;
- проверку того, покрывается ли вопрос текущим корпусом ГК РФ;
- гибридный поиск статей с элементами GraphRAG;
- генерацию ответа с опорой на найденные нормы;
- fact check ответа;
- проверку юридически значимых реплик юриста;
- batch-обработку таблиц с вопросами;
- веб-демонстрацию с live backend;
- предрасчет и кэширование demo payloads.

## 2. Структура проекта

Корень проекта содержит следующие основные каталоги:

- `agents/` — извлечение вопроса, legal domain routing, answer synthesis, fact check, проверка фраз юриста;
- `ingestion/` — подготовка корпуса, парсинг транскриптов, построение summary;
- `rag/` — retrieval, query expansion, reranking, graph-индекс;
- `orchestration/` — LangGraph pipeline, demo-сценарии, batch-скрипты;
- `api/` — backend для веб-демо;
- `ui/` — фронтенд демо-сайта;
- `data/` — корпус, граф, транскрипты, кэшированные payloads;
- `config/` — локальные конфигурационные файлы для Yandex API.

## 3. Системные требования

Минимально рекомендуется:

- Python `3.10+` или `3.11`;
- `pip`;
- доступ в интернет для вызовов Yandex LLM API;
- Windows PowerShell, `cmd`, Linux shell или macOS Terminal.

Проект тестировался как обычный локальный Python-проект без Docker.

## 4. Зависимости

Если проект скачан как отдельный репозиторий или отдельная папка `legal_copilot`, зависимости можно установить напрямую списком пакетов.

Основные библиотеки:

- `langgraph`
- `langchain-core`
- `openai`
- `pypdf`
- `sentence-transformers`

Примечание:

- часть retrieval-логики работает локально;
- LLM-этапы используют внешний API;
- `sentence-transformers` установлен как зависимость, но в некоторых сценариях dense-компоненты могут быть не обязательны.

## 5. Подготовка окружения

### Скачивание проекта с GitHub

Проект хранится в репозитории `legal_copilot`, сначала скачайте его:

```bash
git clone https://github.com/valerrysmi/legal_copilot
cd legal_copilot
```

Если репозиторий уже скачан или открыт локально, просто перейдите в его каталог:

```bash
cd legal_copilot
```

### Вариант A. Windows PowerShell

Сначала перейдите в каталог проекта:

```powershell
cd legal_copilot
```

Создайте виртуальное окружение:

```powershell
python -m venv .venv
```

Активируйте его:

```powershell
.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает выполнение скриптов:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

и затем снова:

```powershell
.venv\Scripts\Activate.ps1
```

Установите зависимости:

```powershell
pip install langgraph langchain-core openai pypdf sentence-transformers
```

### Вариант B. Windows `cmd`

```bat
cd /d legal_copilot
python -m venv .venv
.venv\Scripts\activate.bat
pip install langgraph langchain-core openai pypdf sentence-transformers
```

### Вариант C. Linux / macOS

```bash
cd /path/to/legal_copilot
python3 -m venv .venv
source .venv/bin/activate
pip install langgraph langchain-core openai pypdf sentence-transformers
```

## 6. Настройка Yandex API

Для работы LLM-этапов проект читает конфигурацию из файлов:

- `config/yandex_api_key.txt`
- `config/yandex_folder_id.txt`

В каталоге `config/` уже есть шаблоны:

- `yandex_api_key.txt.example`
- `yandex_folder_id.txt.example`

### Что нужно сделать

Перейдите в каталог проекта:

```powershell
cd legal_copilot
```

Создайте рабочие файлы конфигурации:

```powershell
Copy-Item config\yandex_api_key.txt.example config\yandex_api_key.txt
Copy-Item config\yandex_folder_id.txt.example config\yandex_folder_id.txt
```

Откройте их и вставьте:

- в `config/yandex_api_key.txt` — ваш API-ключ Yandex;
- в `config/yandex_folder_id.txt` — ваш folder id.

Каждый файл должен содержать одно значение без лишнего форматирования.

### Проверка наличия файлов

```powershell
Get-ChildItem config
```

### Переопределение модели через переменную окружения

При необходимости можно явно задать модель:

```powershell
$env:YANDEX_CLOUD_MODEL="gpt://<folder_id>/yandexgpt-lite/latest"
```

Отдельную модель для reranker можно задать аналогично:

```powershell
$env:YANDEX_CLOUD_RERANK_MODEL="gpt://<folder_id>/yandexgpt-lite/latest"
```

Проверить текущие значения:

```powershell
echo $env:YANDEX_CLOUD_MODEL
echo $env:YANDEX_CLOUD_RERANK_MODEL
```

Если переменные не заданы, проект использует значения по умолчанию из кода.

## 7. Где запускать команды

Все команды вида:

```bash
python -m orchestration....
```

нужно запускать из каталога проекта:

```powershell
cd legal_copilot
```

Это важно, потому что внутри проекта используются относительные пути к `data/`, `config/`, `ui/` и другим каталогам.

## 8. Быстрый старт

### 8.1. Один юридический вопрос через LangGraph

```powershell
python -m orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?"
```

Сценарий показывает:

- извлечение вопроса;
- маршрутизацию;
- построение retrieval-запроса;
- поиск статей;
- генерацию ответа;
- fact check;
- рекомендации по дальнейшим действиям.

### 8.2. Обработка транскрипции в консоли

```powershell
python -m orchestration.demo_langgraph --transcript data/transcript_1.txt
```

Ограничить вывод первыми окнами:

```powershell
python -m orchestration.demo_langgraph --transcript data/transcript_1.txt --limit 3
```

### 8.3. Пошаговый streaming demo

```powershell
python -m orchestration.demo_streaming_step_by_step --transcript data/transcript_1.txt
```

### 8.4. Только retrieval по правовым нормам

```powershell
python -m orchestration.demo_graphrag --query "Какие корпоративные голоса нужны для продажи доли в ООО?" --top-k 5
```

## 9. Сохранение вывода demo в текстовый файл

Для основных demo-сценариев поддерживается параметр `--output`.

### Полный demo-прогон по транскрипции

```powershell
python -m orchestration.demo_langgraph --transcript data/transcript_1.txt --output demo_langgraph.txt
```

### Пошаговый streaming demo

```powershell
python -m orchestration.demo_streaming_step_by_step --transcript data/transcript_1.txt --output streaming_demo.txt
```

### Demo по одному вопросу

```powershell
python -m orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?" --output question_demo.txt
```

## 10. Веб-демонстрация

### Запуск backend

Из каталога проекта:

```powershell
python -m api.server
```

После запуска откройте в браузере:

```text
http://127.0.0.1:8000
```

### Что умеет веб-демо

- выбор доступной транскрипции;
- live-обработка сценария через backend;
- пошаговое проигрывание чанков;
- показ найденных статей;
- просмотр текста статьи в модальном окне;
- показ ответов и проверок;
- подсветка реплик юриста, требующих внимания;
- debug- и пользовательский режимы;
- использование предрасчитанных payloads для ускорения загрузки.

## 11. Предрасчет demo payloads

Полный live-прогон длинных транскриптов может быть долгим, поэтому проект умеет заранее сохранять обработанные demo-сценарии в JSON.

### Предрасчет для всех доступных транскриптов

```powershell
python -m orchestration.precompute_demo_payloads
```

### Предрасчет только для одной транскрипции

```powershell
python -m orchestration.precompute_demo_payloads --transcript transcript_1.txt
```

### Принудительное обновление кэша

```powershell
python -m orchestration.precompute_demo_payloads --refresh
```

### Где лежит кэш

Предрасчитанные файлы сохраняются в:

```text
data/demo_payloads/
```

Backend использует их автоматически, если они существуют.

### Принудительный live-пересчет из API

В браузере можно вызвать:

```text
/api/demo?transcript=transcript_1.txt&refresh=1
```

## 12. Подготовка и обновление правового корпуса

### Перегенерация summary статей

Гибридный режим:

```powershell
python -m ingestion.article_summarizer --mode hybrid --overwrite
```

Только эвристический режим:

```powershell
python -m ingestion.article_summarizer --mode heuristic --overwrite
```

### Пересборка графа

```powershell
python -m rag.rebuild_graph
```

### Типичный порядок обновления корпуса

1. Обновить `data/civil_code/articles.json` или связанные summary.
2. Пересобрать `data/civil_code/graph_index.json`.
3. Снова запустить demo или batch-сценарии.

## 13. Основной pipeline

В LangGraph-пайплайне используются основные стадии:

1. `ingest_chunk`
2. `extract_question`
3. `assess_legal_domain`
4. `retrieve`
5. `synthesize_answer`
6. `fact_check`
7. `suggest`

## 14. Программный запуск из Python

Если нужно вызывать проект не через консольные demo, а из собственного скрипта:

```python
from agents.context_manager import StreamingContextManager
from orchestration.graph import run_legal_copilot_turn

session = StreamingContextManager(session_id="demo")
result = run_legal_copilot_turn(
    "Нужно ли нотариальное удостоверение продажи доли в ООО?",
    context_manager=session,
    session_id="demo",
)

print(result.route)
print(result.answer_text)
```

Пример следует запускать из каталога `legal_copilot/`, чтобы импорты и относительные пути работали корректно.

## 15. Batch-обработка таблиц с вопросами

В проекте есть отдельные batch-скрипты:

- `orchestration/batch_answer_legal_questions.py`
- `orchestration/batch_answer_legal_questions_workbook.py`
- `orchestration/format_batch_answers.py`
- `orchestration/format_batch_answers_xlsx.py`

Они используются для:

- прогона набора вопросов;
- сохранения ответов модели;
- формирования отчетов в `md`, `csv` и `xlsx`;
- последующего анализа метрик и качества ответов.

Перед запуском batch-режима стоит:

1. проверить Yandex API-конфиг;
2. убедиться, что корпус и граф актуальны;
3. подготовить входную таблицу с вопросами.

## 16. Основные данные проекта

### Корпус

- `data/civil_code/articles.json`
- `data/civil_code/graph_index.json`

### Демонстрационные транскрипты

- `data/transcript_1.txt`
- `data/transcript_2.txt`
- `data/transcript_3.txt`
- `data/transcript_4.txt`
- `data/transcript_5.txt`
- `data/transcript_6.txt`

## 17. Типичные рабочие команды

### Проверка одного вопроса

```powershell
python -m orchestration.demo_question_langgraph --query "Купил вещь с браком — что могу требовать?"
```

### Проверка retrieval без генерации полного ответа

```powershell
python -m orchestration.demo_graphrag --query "Купил вещь с браком — что могу требовать?" --top-k 5
```

### Пошаговый прогон транскрипции

```powershell
python -m orchestration.demo_streaming_step_by_step --transcript data/transcript_1.txt --limit 3
```

### Пересборка графа

```powershell
python -m rag.rebuild_graph
```

## 18. Что работает локально, а что через API

### Локально

- предобработка текста;
- разбор транскриптов;
- накопление контекста;
- sparse / lexical retrieval;
- graph retrieval;
- базовый reranking;
- fact check;
- проверка реплик юриста;
- backend и UI веб-демо.

### Через внешний API

- генерация ответа;
- LLM query expansion;
- LLM reranking;
- генерация summary статей.

Если API недоступен, часть LLM-сценариев может работать ограниченно или уходить в fallback.

## 19. Частые проблемы и их решение

### Проблема: `ModuleNotFoundError`

Причина:

- команда запущена не из каталога проекта;
- не активировано виртуальное окружение;
- не установлены зависимости.

Решение:

```powershell
cd legal_copilot
```

И убедиться, что активировано окружение и выполнено:

```powershell
pip install langgraph langchain-core openai pypdf sentence-transformers
```

### Проблема: нет ответа от модели

Проверьте:

- заполнены ли `config/yandex_api_key.txt` и `config/yandex_folder_id.txt`;
- есть ли интернет;
- не исчерпаны ли квоты API;
- не задана ли ошибочная переменная `YANDEX_CLOUD_MODEL`.

### Проблема: веб-демо долго грузится

Используйте предрасчет:

```powershell
python -m orchestration.precompute_demo_payloads
```

### Проблема: транскрипция обрабатывается как один большой блок

Убедитесь, что файл транскрипции имеет корректный построчный формат реплик, например:

```text
Client: Добрый день, у меня вопрос по сделке.
Lawyer: Да, слушаю вас.
Client: Нужно ли нотариальное удостоверение?
```

## 20. Ограничения текущей установки

- Проект ориентирован прежде всего на сценарии по ГК РФ.
- Для вопросов из других отраслей права полнота ответов ограничена.
- Качество ответа зависит от текущего корпуса и графа.
- Полный live-прогон длинных транскриптов без кэша может быть заметно медленным.
- Часть сценариев чувствительна к стабильности внешнего LLM API.

## 21. Рекомендуемый порядок первого запуска

Если вы ставите проект впервые, оптимальная последовательность такая:

1. Перейти в каталог `legal_copilot`.
2. Создать и активировать виртуальное окружение.
3. Установить зависимости.
4. Заполнить `config/yandex_api_key.txt` и `config/yandex_folder_id.txt`.
5. Проверить запуск одного вопроса:

```powershell
python -m orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?"
```

6. Проверить demo по транскрипции:

```powershell
python -m orchestration.demo_langgraph --transcript data/transcript_1.txt --limit 3
```

7. При необходимости подготовить кэш:

```powershell
python -m orchestration.precompute_demo_payloads
```

8. После этого запускать веб-демо:

```powershell
python -m api.server
```

## 22. Итог

Для базового запуска проекта достаточно:

- установить Python-зависимости;
- заполнить два конфигурационных файла Yandex;
- запускать команды из каталога `legal_copilot/`.

Минимальный проверочный сценарий:

```powershell
cd legal_copilot
python -m orchestration.demo_question_langgraph --query "Нужно ли нотариальное удостоверение продажи доли в ООО?"
```

После этого можно переходить к транскриптам, batch-режиму и веб-демонстрации.
