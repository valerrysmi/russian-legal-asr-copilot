# Russian Legal ASR Copilot

Единый локальный прототип для обработки юридической консультации в realtime-формате.

Основной сценарий: аудио разбивается на части, ASR распознает очередную реплику, после чего эта часть сразу передается в `legal_copilot` для промежуточного юридического анализа. Не нужно ждать полной транскрипции всей консультации.

Проект объединяет:

- `russian-legal-asr/` - распознавание аудио, VAD, Redis worker-ы, speaker worker;
- `legal_copilot/` - обработка частей транскрипции и юридический анализ;
- `run_realtime_consultation.py` - realtime-связка ASR -> LegalCopilot;
- `unified_server.py` и `unified_ui/` - общий браузерный интерфейс.

## Структура проекта

```text
russian-legal-asr-copilot/
  run_realtime_consultation.py  # основной realtime-запуск
  run_consultation.py           # дополнительный batch-запуск
  unified_server.py             # сервер общего интерфейса
  unified_ui/                   # общий интерфейс в браузере
  russian-legal-asr/            # ASR, VAD, Redis workers
  legal_copilot/                # LegalCopilot pipeline
  requirements*.txt             # профили зависимостей
  .env.example                  # шаблон переменных окружения
```

## Как работает realtime-связка

Основная точка связи находится в:

```text
run_realtime_consultation.py
```

Он использует callback `on_line` из:

```text
russian-legal-asr/gateway/pipeline.py
```

Когда ASR и speaker worker возвращают готовую реплику, `on_line` сразу передает новое окно транскрипции в:

```text
legal_copilot/orchestration/pipeline.py
legal_copilot/orchestration/graph.py
```

Realtime-события сохраняются в:

```text
runs/<consultation>_realtime/realtime_events.jsonl
```

## Установка

Базовые зависимости:

```powershell
python -m pip install -r requirements.txt
```

GigaAM ASR worker:

```powershell
python -m pip install -r requirements-asr-gigaam.txt
```

Speaker worker:

```powershell
python -m pip install -r requirements-speaker.txt
```

Для быстрой проверки без Hugging Face можно запускать speaker worker в режиме `disabled`. Тогда все реплики будут помечены как `Client`, но realtime-пайплайн будет работать.

## 1. Запустить Redis

На Windows без Docker можно использовать Redis внутри WSL:

```powershell
wsl sudo apt update
wsl sudo apt install -y redis-server
wsl redis-server --daemonize yes --bind 0.0.0.0 --protected-mode no --port 6380
```

В PowerShell задайте адрес Redis:

```powershell
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
```

Проверка:

```powershell
python -c "import redis, os; r=redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT'])); print(r.ping())"
```

Ожидаемый результат:

```text
True
```

## 2. Запустить ASR worker

Откройте отдельный PowerShell:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
python -m asr_service.worker
```

Окно нужно оставить открытым.

## 3. Запустить speaker worker

Для быстрого realtime-запуска без Hugging Face:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
$env:SPEAKER_MODE="disabled"
$env:DEFAULT_SPEAKER="Client"
python -m speaker_service.worker
```

Для настоящей идентификации спикеров нужен Hugging Face token и доступ к модели:

```text
https://huggingface.co/pyannote/embedding
```

Токен задается так:

```powershell
$env:HF_TOKEN="hf_..."
```

## 4. Запустить realtime через интерфейс

Откройте третий PowerShell:

```powershell
cd D:\russian-legal-asr-copilot
python .\unified_server.py
```

Откройте в браузере:

```text
http://127.0.0.1:8090
```

В интерфейсе:

1. Выберите консультацию из `data/input`.
2. В поле **Режим запуска** выберите `Realtime: передавать части сразу`.
3. Укажите Redis host и Redis port. Обычно интерфейс подставляет их автоматически.
4. Нажмите **Запустить сессию**.

Параметр **Realtime factor**:

- `0` - обрабатывать файл максимально быстро;
- `1` - имитировать реальное время;
- `0.1` - примерно в 10 раз быстрее реального времени.

## 5. Запустить realtime через CLI

```powershell
cd D:\russian-legal-asr-copilot
$redisHost = (wsl hostname -I).Trim().Split()[0]
python .\run_realtime_consultation.py --consultation consultation1 --redis-host $redisHost --redis-port 6380
```

Имитировать реальное время:

```powershell
python .\run_realtime_consultation.py --consultation consultation1 --redis-host $redisHost --redis-port 6380 --realtime-factor 1
```

## Где лежат результаты realtime-запуска

```text
runs/<consultation>_realtime/
  transcript.txt           # итоговая транскрипция
  timings.json             # тайминги ASR pipeline
  realtime_events.jsonl    # события LegalCopilot по мере поступления частей
```

Каждая строка `realtime_events.jsonl` - отдельное JSON-событие. Основной тип события:

```json
{
  "type": "copilot_update",
  "seq": 1,
  "speaker": "Client",
  "text": "...",
  "active_user_query": "...",
  "route": "...",
  "answer_text": "..."
}
```

## Формат входных аудио

Интерфейс и CLI ищут аудио в:

```text
russian-legal-asr/data/input/<consultation>/
```

Поддерживаемые расширения:

```text
.mp3, .m4a, .wav, .flac, .ogg, .opus, .aac, .wma
```

## Batch-запуск

Batch-режим оставлен как дополнительный вариант: сначала создается полный `transcript.txt`, затем он целиком передается в LegalCopilot.

Через интерфейс выберите режим:

```text
Batch: сначала вся транскрипция
```

Через CLI:

```powershell
python .\run_consultation.py --consultation consultation1
```

Только обработка готовой транскрипции:

```powershell
python .\run_consultation.py --skip-asr --transcript .\runs\consultation1\transcript.txt
```

## Секреты и локальные файлы

Скопируйте `.env.example` в `.env` и заполните локальные значения при необходимости.

Не коммитьте:

- `.env`;
- Hugging Face token;
- Yandex API keys;
- аудиофайлы консультаций;
- папку `runs/`;
- model checkpoints и большие бинарные файлы.

## Подготовка к публикации в отдельный репозиторий

Внутри `legal_copilot/` может быть вложенный Git-репозиторий. Если нужен один общий monorepo и история вложенного репозитория не важна:

```powershell
Remove-Item -Recurse -Force .\legal_copilot\.git
```

Затем:

```powershell
git init
git add .
git commit -m "Initial realtime ASR copilot project"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

Перед публикацией проверьте, что в индекс не попали аудио, токены, логи и результаты запусков.
