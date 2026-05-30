# MVP site prototype: Telegram lead intake

## Что уже сделано
- многостраничный сайт под бренд «АкваСтрой»
- отдельные посадочные страницы под каждую ключевую услугу
- главная как маршрутизатор по услугам: помогает быстро выбрать нужное направление
- формы заявок на каждой странице
- MVP-калькулятор на главной для предварительного ориентира по скважине
- два совместимых обработчика заявок:
  - `server.py` для локального предпросмотра и Python-режима
  - `api/lead.php` для простого shared hosting, в том числе бесплатного REG.RU
- backend формы умеет:
  - отправлять заявку в Telegram, если заполнены настройки
  - сохранять каждую заявку в резервный лог `data/leads.jsonl`
  - возвращать `lead_id`, статус доставки и диагностические подсказки
  - работать в preview-режиме, если Telegram ещё не настроен

## Структура файлов
- `index.html` — главная / маршрутизатор по услугам
- `burenie-skvazhin.html` — бурение скважин
- `skvazhina-pod-klyuch.html` — скважина под ключ
- `obustroystvo-skvazhin.html` — обустройство скважины
- `vodopodgotovka.html` — водоподготовка
- `nasosnoe-oborudovanie.html` — насосное оборудование
- `remont-nasosov.html` — ремонт насосов
- `avtopoliv.html` — автополив
- `otoplenie.html` — отопление
- `style.css` — стили
- `app.js` — фронтенд логика форм с авто-переключением между `/api/lead` и `/api/lead.php`
- `server.py` — локальный сервер + Python API для заявок
- `api/bootstrap.php` — общие функции PHP-обработчика
- `api/lead.php` — обработчик заявок для shared hosting / REG.RU
- `api/config.php.example` — шаблон настроек Telegram для PHP-версии
- `AD_LAUNCH_MAP.md` — приоритет страниц и рекламных запусков
- `DOMAIN_SETUP.md` — подготовка проекта к домену, DNS-шаги и пример Caddy-конфига
- `.env.example` — пример локальных настроек для `server.py`

## Запуск
```bash
cd /home/art/04_ai_agents/kazan_well_marketing/prototype
cp .env.example .env
python3 server.py
```

После запуска:
- сайт: `http://127.0.0.1:8765/index.html`
- формы отправляют данные в `POST /api/lead`
- резервный лог: `data/leads.jsonl`

## Telegram
### Локальный Python-режим
Чтобы заявки реально улетали в Telegram при запуске `server.py`, в `.env` нужно заполнить:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Если они пустые, сайт работает в preview-режиме:
- заявка всё равно сохраняется в `data/leads.jsonl`
- пользователь получает `lead_id`
- фронтенд показывает предпросмотр сообщения и статус `preview`

### REG.RU / PHP-режим
Для хостинга без Python:
1. Скопируйте `api/config.php.example` в `api/config.php`
2. Впишите туда:
   - `site_name`
   - `telegram_bot_token`
   - `telegram_chat_id`
3. Убедитесь, что папка `data/` доступна на запись

Фронтенд сам пробует:
- сначала `api/lead.php` на обычном хостинге
- а локально сначала `/api/lead` через `server.py`

## Что попадает в заявку
В резервный лог и в Telegram уходит:
- `lead_id`
- время отправки
- сайт / бренд
- имя
- телефон
- населённый пункт
- что нужно
- комментарий
- страница
- источник перехода

## Следующие практические шаги
- загрузить сайт на REG.RU вместе с папкой `api/`
- создать на хостинге `api/config.php` по образцу `api/config.php.example`
- проверить, что папка `data/` доступна на запись
- после публикации отправить тестовую заявку и проверить Telegram
- добавить антиспам
- продумать CRM / Google Sheets как второй канал кроме Telegram
- сделать geo-pages под приоритетные посёлки после запуска рекламы
