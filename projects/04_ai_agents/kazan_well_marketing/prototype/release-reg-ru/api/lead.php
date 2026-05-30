<?php

require __DIR__ . '/bootstrap.php';

if (!isset($_SERVER['REQUEST_METHOD']) || $_SERVER['REQUEST_METHOD'] !== 'POST') {
    lead_json_response(405, array('error' => 'Method not allowed'));
}

$raw = file_get_contents('php://input');
$payload = json_decode($raw ? $raw : '', true);
if (!is_array($payload)) {
    lead_json_response(400, array('error' => 'Некорректный JSON'));
}

$name = trim(isset($payload['name']) ? (string) $payload['name'] : '');
$phone = trim(isset($payload['phone']) ? (string) $payload['phone'] : '');
if ($name === '' || $phone === '') {
    lead_json_response(400, array('error' => 'Нужны имя и телефон'));
}

if (!isset($payload['submitted_at'])) {
    $payload['submitted_at'] = lead_now_iso();
}

$settings = lead_settings();
$preview = lead_build_message($payload, $settings['site_name']);
$botToken = $settings['telegram_bot_token'];
$chatId = $settings['telegram_chat_id'];

if ($botToken !== '' && $chatId !== '') {
    list($ok, $detail) = lead_send_to_telegram($botToken, $chatId, $preview);
    $logEntry = lead_append_log($settings, $payload, $ok ? 'sent' : 'failed', $detail, $preview);

    if (!$ok) {
        lead_json_response(502, array(
            'error' => 'Telegram не принял сообщение',
            'details' => $detail,
            'lead_id' => $logEntry['lead_id'],
            'log_path' => 'data/leads.jsonl',
            'preview' => $preview,
        ));
    }

    lead_json_response(200, array(
        'ok' => true,
        'message' => 'Заявка отправлена в Telegram и сохранена в резервный лог.',
        'telegram_status' => 'sent',
        'lead_id' => $logEntry['lead_id'],
        'log_path' => 'data/leads.jsonl',
        'preview' => $preview,
    ));
}

$logEntry = lead_append_log(
    $settings,
    $payload,
    'preview',
    array(
        'kind' => 'preview_mode',
        'message' => 'Telegram не настроен: заявка сохранена только в резервный лог.',
    ),
    $preview
);

lead_json_response(200, array(
    'ok' => true,
    'message' => 'Заявка сохранена в резервный лог. Telegram сейчас не настроен.',
    'telegram_status' => 'preview',
    'lead_id' => $logEntry['lead_id'],
    'log_path' => 'data/leads.jsonl',
    'preview' => $preview,
));
