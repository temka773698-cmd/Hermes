# REG.RU deployment bundle

Готовая папка для заливки на обычный shared hosting REG.RU:

- `index.html`
- `style.css`
- `script.js`
- `api/chat.php`
- `api/config.php.example`
- `storage/` — файлы сессий и лог заявок

## Что изменено под shared hosting

- убран Python backend из runtime-цепочки деплоя;
- фронтенд переключён на `./api/chat.php`;
- диалог и сбор фактов перенесены в PHP;
- сохранение сессий идёт в `storage/sessions/*.json`;
- заявки пишутся в `storage/leads/leads.jsonl`;
- Telegram-отправка идёт напрямую через Bot API из PHP;
- `storage/.htaccess` закрывает прямой доступ к данным.

## Как залить на REG.RU

1. Открой файловый менеджер REG.RU или подключись по FTP/SFTP.
2. Перейди в корень сайта: обычно `public_html/` или `www/`.
3. Залей **содержимое** этой папки `reg_ru_upload/` в корень сайта.
4. Открой на сервере файл `api/config.php`.
5. Заполни в `api/config.php`:
   - `telegram_bot_token`
   - `telegram_group_chat_id`
6. Проверь права записи:
   - папка `storage/`
   - папка `storage/sessions/`
   - папка `storage/leads/`

Обычно хватает `755`, но если хостинг не даёт писать, поставь на `storage`, `storage/sessions`, `storage/leads` права `775`.

## Минимальный `api/config.php`

```php
<?php
return [
    'site_name' => 'АкваСтрой',
    'telegram_bot_token' => '123456:ABC...',
    'telegram_group_chat_id' => '-1001234567890',
    'timezone' => 'Europe/Moscow',
];
```

## Быстрая проверка после заливки

1. Открой главную страницу сайта.
2. Убедись, что чат сам пишет первое приветствие.
3. Пройди короткий тестовый диалог.
4. Проверь:
   - пришла ли заявка в Telegram;
   - появился ли файл `storage/leads/leads.jsonl`;
   - появились ли JSON-файлы в `storage/sessions/`.

## Если Telegram не отправляет

Проверь по порядку:

1. токен бота правильный;
2. бот добавлен в группу;
3. у бота есть право писать в группу;
4. `telegram_group_chat_id` указан правильно;
5. на хостинге включён исходящий HTTPS.

## Важное ограничение

Этот bundle рассчитан именно на обычный PHP shared hosting.
Он **не использует** `app.py` и не требует постоянного Python-процесса.
