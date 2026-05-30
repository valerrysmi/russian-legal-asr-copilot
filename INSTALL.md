# Установка и запуск

Эта инструкция описывает основной realtime-сценарий: аудио распознается частями, и каждая готовая часть сразу передается в LegalCopilot.

Команды ниже рассчитаны на Windows PowerShell и проект в папке:

```text
D:\russian-legal-asr-copilot
```

Если проект лежит в другой папке, замените путь в командах.

## 1. Подготовить Python

Рекомендуется Python 3.11.

Проверьте версию:

```powershell
python --version
```

Перейдите в корень проекта:

```powershell
cd D:\russian-legal-asr-copilot
```

Установите базовые зависимости:

```powershell
python -m pip install -r requirements.txt
```

Установите зависимости ASR worker:

```powershell
python -m pip install -r requirements-asr-gigaam.txt
```

Установите зависимости speaker worker:

```powershell
python -m pip install -r requirements-speaker.txt
```

Если нужен Whisper ASR вместо GigaAM:

```powershell
python -m pip install -r requirements-asr-whisper.txt
```

## 2. Установить ffmpeg

Для чтения `.m4a`, `.mp3` и других аудиоформатов нужен `ffmpeg`.

Установка через winget:

```powershell
winget install Gyan.FFmpeg
```

После установки закройте и заново откройте PowerShell.

Проверка:

```powershell
ffmpeg -version
```

## 3. Запустить Redis

Если Docker не установлен, используйте Redis внутри WSL.

Установить Redis в WSL:

```powershell
wsl sudo apt update
wsl sudo apt install -y redis-server
```

Запустить Redis на порту `6380`:

```powershell
wsl redis-server --daemonize yes --bind 0.0.0.0 --protected-mode no --port 6380
```

В PowerShell получить адрес WSL и сохранить переменные окружения:

```powershell
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
```

Проверить подключение:

```powershell
python -c "import redis, os; r=redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT'])); print(r.ping())"
```

Ожидаемый результат:

```text
True
```

## 4. Подготовить аудио консультации

Положите аудиофайл в папку:

```text
russian-legal-asr/data/input/consultation1/
```

Пример:

```text
russian-legal-asr/data/input/consultation1/consultation.m4a
```

Поддерживаемые форматы:

```text
.mp3, .m4a, .wav, .flac, .ogg, .opus, .aac, .wma
```

Если в папке лежит больше одного аудиофайла, при CLI-запуске укажите файл явно через `--audio`.

## 5. Запустить ASR worker

Откройте отдельное окно PowerShell:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
python -m asr_service.worker
```

Оставьте это окно открытым.

Если используете Whisper ASR:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
python -m asr_service_whisper.worker
```

Запускать нужно только один ASR worker: GigaAM или Whisper.

## 6. Запустить speaker worker

Для быстрого запуска без Hugging Face:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
$env:SPEAKER_MODE="disabled"
$env:DEFAULT_SPEAKER="Client"
python -m speaker_service.worker
```

Оставьте это окно открытым.

В этом режиме все реплики будут помечены как `Client`.

Для настоящей идентификации спикеров:

1. Создайте Hugging Face access token:

```text
https://huggingface.co/settings/tokens
```

2. Примите условия доступа к модели:

```text
https://huggingface.co/pyannote/embedding
```

3. Запустите speaker worker с токеном:

```powershell
cd D:\russian-legal-asr-copilot\russian-legal-asr
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
$env:SPEAKER_MODE="diarization"
$env:HF_TOKEN="hf_..."
python -m speaker_service.worker
```

## 7. Запустить общий realtime-интерфейс

Откройте третье окно PowerShell:

```powershell
cd D:\russian-legal-asr-copilot
python .\unified_server.py
```

Откройте браузер:

```text
http://127.0.0.1:8090
```

В интерфейсе:

1. Выберите консультацию, например `consultation1`.
2. Выберите режим `Realtime: передавать части сразу`.
3. Проверьте Redis host и Redis port.
4. Нажмите `Запустить сессию`.

Параметр `Realtime factor`:

- `0` - обработка максимально быстро;
- `1` - имитация реального времени;
- `0.1` - примерно в 10 раз быстрее реального времени.

## 8. Запуск realtime через CLI

Вместо интерфейса можно запустить realtime-пайплайн командой:

```powershell
cd D:\russian-legal-asr-copilot
$redisHost = (wsl hostname -I).Trim().Split()[0]
python .\run_realtime_consultation.py --consultation consultation1 --redis-host $redisHost --redis-port 6380
```

С имитацией реального времени:

```powershell
python .\run_realtime_consultation.py --consultation consultation1 --redis-host $redisHost --redis-port 6380 --realtime-factor 1
```

Если нужно указать аудиофайл явно:

```powershell
python .\run_realtime_consultation.py --consultation consultation1 --audio ".\russian-legal-asr\data\input\consultation1\consultation.m4a" --redis-host $redisHost --redis-port 6380
```

## 9. Где смотреть результаты

Realtime-запуск сохраняет файлы в:

```text
runs/consultation1_realtime/
```

Основные файлы:

```text
transcript.txt           итоговая транскрипция
timings.json             тайминги ASR pipeline
realtime_events.jsonl    события LegalCopilot по мере поступления частей
```

Batch-запуск сохраняет файлы в:

```text
runs/consultation1/
```

## 10. Частые проблемы

### Redis connection refused

Redis не запущен или указан неправильный порт.

Проверьте:

```powershell
$redisHost = (wsl hostname -I).Trim().Split()[0]
$env:REDIS_HOST=$redisHost
$env:REDIS_PORT="6380"
python -c "import redis, os; r=redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT'])); print(r.ping())"
```

### ModuleNotFoundError

Не установлены зависимости нужной части.

Проверьте, какой worker падает, и установите соответствующий файл:

```powershell
python -m pip install -r requirements-asr-gigaam.txt
python -m pip install -r requirements-speaker.txt
python -m pip install -r requirements.txt
```

### Не скачивается pyannote/embedding

Для pyannote нужен Hugging Face token и принятие условий модели.

Для проверки без pyannote используйте:

```powershell
$env:SPEAKER_MODE="disabled"
```

### Аудиофайл не читается

Проверьте `ffmpeg`:

```powershell
ffmpeg -version
```

Если команды нет, установите:

```powershell
winget install Gyan.FFmpeg
```
