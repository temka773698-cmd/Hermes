<?php

function lead_base_dir()
{
    return dirname(__DIR__);
}

function lead_string_starts_with($haystack, $needle)
{
    return $needle === '' || strpos($haystack, $needle) === 0;
}

function lead_string_contains($haystack, $needle)
{
    return $needle !== '' && strpos($haystack, $needle) !== false;
}

function lead_load_env($path)
{
    if (!is_file($path)) {
        return array();
    }

    $values = array();
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!is_array($lines)) {
        return $values;
    }

    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '' || lead_string_starts_with($line, '#') || !lead_string_contains($line, '=')) {
            continue;
        }
        list($key, $value) = explode('=', $line, 2);
        $values[trim($key)] = trim($value);
    }

    return $values;
}

function lead_settings()
{
    $baseDir = lead_base_dir();
    $env = lead_load_env($baseDir . '/.env');
    $configPath = __DIR__ . '/config.php';
    $config = is_file($configPath) ? require $configPath : array();
    if (!is_array($config)) {
        $config = array();
    }

    return array(
        'site_name' => trim(isset($config['site_name']) ? $config['site_name'] : (isset($env['SITE_NAME']) ? $env['SITE_NAME'] : 'АкваСтрой')),
        'telegram_bot_token' => trim(isset($config['telegram_bot_token']) ? $config['telegram_bot_token'] : (isset($env['TELEGRAM_BOT_TOKEN']) ? $env['TELEGRAM_BOT_TOKEN'] : '')),
        'telegram_chat_id' => trim(isset($config['telegram_chat_id']) ? $config['telegram_chat_id'] : (isset($env['TELEGRAM_CHAT_ID']) ? $env['TELEGRAM_CHAT_ID'] : '')),
        'leads_dir' => $baseDir . '/data',
        'leads_log_path' => $baseDir . '/data/leads.jsonl',
    );
}

function lead_now_iso()
{
    return gmdate('c');
}

function lead_clean_value($value)
{
    $text = trim((string) $value);
    return $text !== '' ? $text : '-';
}

function lead_normalize_source_url($value)
{
    $text = trim((string) $value);
    if ($text === '') {
        return $text;
    }

    $preferredHost = 'аквастрой-казань.рф';
    $punycodeHost = 'xn----7sbabai2bnge0bfznp3o.xn--p1ai';

    return str_replace('://' . $punycodeHost, '://' . $preferredHost, $text);
}

function lead_build_message($payload, $siteName)
{
    $submittedAt = lead_clean_value(isset($payload['submitted_at']) ? $payload['submitted_at'] : '');
    $source = lead_clean_value(lead_normalize_source_url(isset($payload['source']) ? $payload['source'] : ''));

    $lines = array(
        '💧 Новая заявка с сайта',
        'Бренд: ' . lead_clean_value($siteName),
        'Имя: ' . lead_clean_value(isset($payload['name']) ? $payload['name'] : ''),
        'Телефон: ' . lead_clean_value(isset($payload['phone']) ? $payload['phone'] : ''),
        'Населённый пункт: ' . lead_clean_value(isset($payload['location']) ? $payload['location'] : ''),
        'Что нужно: ' . lead_clean_value(isset($payload['need']) ? $payload['need'] : ''),
        'Комментарий: ' . lead_clean_value(isset($payload['comment']) ? $payload['comment'] : ''),
        '',
        'Технические детали',
        'Страница: ' . lead_clean_value(isset($payload['page']) ? $payload['page'] : ''),
        'Источник: ' . $source,
        'Время: ' . $submittedAt,
    );

    return implode("\n", $lines);
}

function lead_append_log($settings, $payload, $telegramStatus, $telegramDetail, $preview)
{
    if (!is_dir($settings['leads_dir'])) {
        mkdir($settings['leads_dir'], 0775, true);
    }

    $entry = array(
        'lead_id' => bin2hex(random_bytes(6)),
        'created_at' => lead_now_iso(),
        'site_name' => $settings['site_name'],
        'payload' => $payload,
        'telegram_status' => $telegramStatus,
        'telegram_detail' => $telegramDetail,
        'preview' => $preview,
    );

    file_put_contents(
        $settings['leads_log_path'],
        json_encode($entry, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL,
        FILE_APPEND | LOCK_EX
    );

    return $entry;
}

function lead_lower($value)
{
    if (function_exists('mb_strtolower')) {
        return mb_strtolower($value, 'UTF-8');
    }
    return strtolower($value);
}

function lead_telegram_hint($statusCode, $description)
{
    $desc = lead_lower((string) $description);
    if ($statusCode === 400 && lead_string_contains($desc, 'chat not found')) {
        return 'Скорее всего неверный telegram_chat_id: бот не видит чат или chat_id указан с ошибкой.';
    }
    if ($statusCode === 400 && lead_string_contains($desc, 'message is too long')) {
        return 'Сообщение слишком длинное. Нужно сократить текст заявки или обрезать комментарий.';
    }
    if ($statusCode === 401) {
        return 'Похоже, неверный telegram_bot_token. Проверьте токен в api/config.php.';
    }
    if ($statusCode === 403) {
        return 'Бот не может писать в этот чат. Добавьте бота в чат или начните с ним диалог и проверьте права.';
    }
    if ($statusCode === 429) {
        return 'Telegram временно ограничил отправку. Подождите и попробуйте снова.';
    }
    return 'Проверьте telegram_bot_token, telegram_chat_id и ответ Telegram API.';
}

function lead_send_to_telegram($botToken, $chatId, $text)
{
    $url = 'https://api.telegram.org/bot' . rawurlencode($botToken) . '/sendMessage';
    $body = http_build_query(
        array(
            'chat_id' => $chatId,
            'text' => $text,
            'disable_web_page_preview' => 'true',
        ),
        '',
        '&'
    );

    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, array(
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $body,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 10,
            CURLOPT_TIMEOUT => 20,
            CURLOPT_HTTPHEADER => array('Content-Type: application/x-www-form-urlencoded'),
        ));
        $responseBody = curl_exec($ch);
        $statusCode = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        if ($responseBody === false) {
            $curlError = curl_error($ch);
            curl_close($ch);
            return array(false, array(
                'kind' => 'telegram_transport_error',
                'message' => 'Ошибка cURL при обращении к Telegram: ' . ($curlError !== '' ? $curlError : 'без описания'),
                'status_code' => $statusCode ?: null,
                'telegram_description' => '',
                'response_body' => false,
                'hint' => 'Проверьте, может ли хостинг выполнять исходящие HTTPS-запросы и поддерживает ли cURL.',
            ));
        }
        curl_close($ch);

        $decoded = json_decode($responseBody, true);
        if (($statusCode >= 200 && $statusCode < 300) && is_array($decoded) && !empty($decoded['ok'])) {
            return array(true, $decoded);
        }

        $description = is_array($decoded) && isset($decoded['description']) ? (string) $decoded['description'] : '';
        return array(false, array(
            'kind' => 'telegram_api_error',
            'message' => 'Telegram API отклонил сообщение: ' . ($description !== '' ? $description : 'без описания'),
            'status_code' => $statusCode ?: null,
            'telegram_description' => $description,
            'response_body' => $decoded !== null ? $decoded : $responseBody,
            'hint' => lead_telegram_hint($statusCode ?: null, $description),
        ));
    }

    $context = stream_context_create(array(
        'http' => array(
            'method' => 'POST',
            'header' => "Content-Type: application/x-www-form-urlencoded\r\n" .
                'Content-Length: ' . strlen($body) . "\r\n",
            'content' => $body,
            'timeout' => 20,
            'ignore_errors' => true,
        ),
    ));

    $responseBody = @file_get_contents($url, false, $context);
    $statusCode = null;
    if (isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $matches)) {
        $statusCode = (int) $matches[1];
    }

    $decoded = is_string($responseBody) ? json_decode($responseBody, true) : null;
    if (($statusCode !== null && $statusCode >= 200 && $statusCode < 300) && is_array($decoded) && !empty($decoded['ok'])) {
        return array(true, $decoded);
    }

    $description = is_array($decoded) && isset($decoded['description']) ? (string) $decoded['description'] : '';
    return array(false, array(
        'kind' => 'telegram_api_error',
        'message' => 'Telegram API отклонил сообщение: ' . ($description !== '' ? $description : 'без описания'),
        'status_code' => $statusCode,
        'telegram_description' => $description,
        'response_body' => $decoded !== null ? $decoded : $responseBody,
        'hint' => lead_telegram_hint($statusCode, $description),
    ));
}

function lead_json_response($status, $payload)
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
