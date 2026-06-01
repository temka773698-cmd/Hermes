<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

const BASE_DIR = __DIR__ . '/..';
const STORAGE_DIR = BASE_DIR . '/storage';
const LEADS_PATH = STORAGE_DIR . '/leads/leads.jsonl';
const SESSIONS_DIR = STORAGE_DIR . '/sessions';

try {
    bootstrap_storage();

    $config = load_config(__DIR__ . '/config.php');
    if (!empty($config['timezone'])) {
        @date_default_timezone_set((string) $config['timezone']);
    }

    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
        send_json(['error' => 'Method not allowed'], 405);
    }

    $raw = file_get_contents('php://input');
    $payload = json_decode($raw ?: '{}', true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($payload)) {
        $payload = [];
    }

    $sessionId = sanitize_session_id((string) ($payload['session_id'] ?? ''));
    if ($sessionId === '') {
        $sessionId = generate_session_id();
    }

    $message = trim((string) ($payload['message'] ?? ''));
    $state = load_state($sessionId);

    if ($message === '' && count($state['messages']) === 0) {
        $reply = start_reply();
        add_message($state, 'assistant', $reply);
        save_state($sessionId, $state);
        send_json([
            'session_id' => $sessionId,
            'reply' => $reply,
            'state' => serialize_state($state),
        ]);
    }

    if ($message === '') {
        send_json([
            'session_id' => $sessionId,
            'reply' => 'Напишите сообщение, и я продолжу диалог.',
            'state' => serialize_state($state),
        ]);
    }

    $wasReady = is_ready_for_handoff($state);
    add_message($state, 'user', $message);
    extract_facts($state, $message);

    if (is_ready_for_handoff($state)) {
        $reply = "Спасибо, основные данные собраны. Передаю заявку менеджеру.\n\n" . extract_lead_summary($state);
    } else {
        $reply = next_question($state);
    }

    add_message($state, 'assistant', $reply);

    $telegramStatus = null;
    if (is_ready_for_handoff($state) && !$wasReady && empty($state['lead_sent'])) {
        $summary = extract_lead_summary($state);
        append_lead([
            'session_id' => $sessionId,
            'summary' => $summary,
            'facts' => $state['facts'],
        ]);
        $telegramStatus = notify_telegram($config, $summary);
        $state['lead_sent'] = true;
    }

    save_state($sessionId, $state);

    send_json([
        'session_id' => $sessionId,
        'reply' => $reply,
        'state' => serialize_state($state),
        'telegram_status' => $telegramStatus,
    ]);
} catch (Throwable $e) {
    send_json(['error' => $e->getMessage()], 500);
}

function bootstrap_storage(): void
{
    $directories = [
        STORAGE_DIR,
        dirname(LEADS_PATH),
        SESSIONS_DIR,
    ];

    foreach ($directories as $directory) {
        if (!is_dir($directory) && !mkdir($directory, 0775, true) && !is_dir($directory)) {
            throw new RuntimeException('Не удалось создать директорию: ' . $directory);
        }
    }
}

function load_config(string $path): array
{
    if (!is_file($path)) {
        return [];
    }

    $config = require $path;
    return is_array($config) ? $config : [];
}

function sanitize_session_id(string $sessionId): string
{
    return preg_replace('/[^a-zA-Z0-9_-]/', '', $sessionId) ?? '';
}

function generate_session_id(): string
{
    return bin2hex(random_bytes(16));
}

function state_path(string $sessionId): string
{
    return SESSIONS_DIR . '/' . $sessionId . '.json';
}

function load_state(string $sessionId): array
{
    $path = state_path($sessionId);
    if (!is_file($path)) {
        return [
            'messages' => [],
            'facts' => [],
            'lead_sent' => false,
        ];
    }

    $decoded = json_decode((string) file_get_contents($path), true);
    if (!is_array($decoded)) {
        return [
            'messages' => [],
            'facts' => [],
            'lead_sent' => false,
        ];
    }

    $decoded['messages'] = is_array($decoded['messages'] ?? null) ? $decoded['messages'] : [];
    $decoded['facts'] = is_array($decoded['facts'] ?? null) ? $decoded['facts'] : [];
    $decoded['lead_sent'] = (bool) ($decoded['lead_sent'] ?? false);
    return $decoded;
}

function save_state(string $sessionId, array $state): void
{
    $encoded = json_encode($state, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    if ($encoded === false) {
        throw new RuntimeException('Не удалось сериализовать состояние сессии.');
    }

    if (file_put_contents(state_path($sessionId), $encoded, LOCK_EX) === false) {
        throw new RuntimeException('Не удалось сохранить состояние сессии.');
    }
}

function send_json(array $payload, int $status = 200): void
{
    http_response_code($status);
    $json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($json === false) {
        $json = '{"error":"JSON encode error"}';
    }
    echo $json;
    exit;
}

function serialize_state(array $state): array
{
    return [
        'messages' => $state['messages'],
        'facts' => $state['facts'],
        'ready_for_handoff' => is_ready_for_handoff($state),
    ];
}

function start_reply(): string
{
    return 'Здравствуйте! Я помогу собрать данные для подбора насоса. Для какой задачи нужен насос: скважина, колодец, дренаж, канализация или что-то другое?';
}

function add_message(array &$state, string $role, string $content): void
{
    $state['messages'][] = ['role' => $role, 'content' => $content];
}

function extract_facts(array &$state, string $text): void
{
    $low = mb_strtolower($text, 'UTF-8');
    $normalized = trim($low, " .,!?:;—-\t\n\r\0\x0B");
    $facts = &$state['facts'];

    $facts['raw_request'] = trim(($facts['raw_request'] ?? '') . "\n" . $text);

    if (contains_any($low, ['скваж'])) {
        $facts['task'] = 'Скважинный насос';
    } elseif (contains_any($low, ['колод'])) {
        $facts['task'] = 'Колодезный насос';
    } elseif (contains_any($low, ['дренаж', 'откач', 'ливн', 'лявн', 'подвал', 'добвал'])) {
        $facts['task'] = 'Дренажный насос';
    } elseif (contains_any($low, ['канализа', 'фекал'])) {
        $facts['task'] = 'Канализационный/фекальный насос';
    } elseif (contains_any($low, ['давлен', 'центральн', 'централ'])) {
        $facts['task'] = 'Повышение давления';
    }

    if (preg_match('/(?<!\d)(?:(?:\+7|8)[\s\-\(\)]*)?\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)/u', $text, $match)) {
        $facts['contact'] = trim($match[0]);
    }

    if (preg_match('/(?:меня\s+зовут\s+|^я\s+)([А-ЯЁA-Z][а-яёa-z]{2,})/u', $text, $match)) {
        $facts['name'] = $match[1];
    }

    if (preg_match('/(?:город|из)\s+([А-ЯЁA-Z][а-яёa-z\- ]{2,})/u', $text, $match)) {
        $facts['city'] = trim($match[1]);
    }

    $taskKnown = !empty($facts['task']);
    $fullKitAnswers = ['полный', 'полная', 'полное', 'да', 'надо', 'нужно', 'вместе', 'вмести', 'все', 'всё'];

    if (contains_any($low, ['насосная станц']) || $normalized === 'станция') {
        if (contains_any($low, ['защит', 'холост', 'ход'])) {
            $facts['scope'] = 'Насосная станция с защитой';
        } else {
            $facts['scope'] = 'Насосная станция';
        }
    } elseif (contains_text($low, 'комплект') || ($taskKnown && empty($facts['scope']) && in_array($normalized, $fullKitAnswers, true))) {
        $facts['scope'] = 'Полный комплект';
    } elseif (contains_any($low, ['только насос', 'один насос']) || ($taskKnown && $normalized === 'насос')) {
        $facts['scope'] = 'Только насос';
    }

    if (contains_any($low, ['подвал', 'добвал'])) {
        $facts['drainage_place'] = 'Подвал';
    } elseif (contains_text($low, 'погреб')) {
        $facts['drainage_place'] = 'Погреб';
    } elseif (contains_any($low, ['участ', 'двор', 'канава'])) {
        $facts['drainage_place'] = 'Участок/улица';
    }

    if (($facts['task'] ?? '') === 'Дренажный насос') {
        if (contains_any($low, ['ливн', 'лявн', 'дожд'])) {
            $facts['drainage_water'] = 'Дождевая/ливневая вода';
        } elseif (contains_text($low, 'гряз')) {
            $facts['drainage_water'] = 'Грязная вода';
        } elseif (contains_text($low, 'чист')) {
            $facts['drainage_water'] = 'Чистая вода';
        }

        if (preg_match('/(?:глубин|яма|приям|уровень)\D{0,15}(\d{1,3})\s*(?:м|метр|см)?/u', $low, $match)) {
            $facts['drainage_depth'] = $match[1];
        }
    }

    if (contains_any($low, ['водоочист', 'водоподготов', 'анализ воды', 'анализ', 'фильтр'])) {
        $treatmentNeeded = preg_match('/(?:водоочист\w*|водоподготов\w*|фильтр\w*)\D{0,20}(?:нуж|над|да|есть)/u', $low) === 1;
        $treatmentNotNeeded = preg_match('/(?:водоочист\w*|водоподготов\w*|фильтр\w*)\D{0,20}(?:не\s+нуж|нет|без)/u', $low) === 1;
        $analysisExists = preg_match('/анализ\w*(?:\s+воды)?\D{0,20}(?:есть|имеется|да)/u', $low) === 1;
        $analysisMissing = preg_match('/анализ\w*(?:\s+воды)?\D{0,20}(?:нет|не\s+делал|не\s+сдавал|отсутств)/u', $low) === 1;

        if ($treatmentNotNeeded || $analysisMissing) {
            $facts['water_treatment'] = $analysisMissing ? 'Не нужна, анализа нет' : 'Не нужна';
        } elseif ($treatmentNeeded || $analysisExists) {
            $facts['water_treatment'] = $analysisExists ? 'Нужна, анализ есть' : 'Нужна';
        } else {
            $facts['water_treatment'] = 'Ответ по водоочистке получен';
        }
    }

    if (contains_any($low, ['дом', 'дач', 'бан'])) {
        $facts['object_type'] = contains_text($low, 'бан') ? 'Баня' : 'Дом/дача';
    }
    if (contains_text($low, 'полив')) {
        $facts['usage_points'] = 'Полив';
    }
    if (contains_any($low, ['всего дом', 'весь дом'])) {
        $facts['usage_points'] = 'Весь дом';
    }

    if (preg_match('/^(\d{1,2})\s*[-–—]\s*(\d{1,2})$/u', $normalized, $rangeMatch)) {
        $facts['bathrooms'] = $rangeMatch[1] . '-' . $rangeMatch[2];
    }

    $numberWords = [
        'один' => '1', 'одна' => '1', 'два' => '2', 'две' => '2', 'три' => '3', 'четыре' => '4',
        'пять' => '5', 'шесть' => '6', 'семь' => '7', 'восемь' => '8', 'девять' => '9', 'десять' => '10',
    ];
    $bareNumber = preg_match('/^\d{1,2}$/u', $normalized) === 1 ? $normalized : null;
    $wordNumber = $numberWords[$normalized] ?? null;

    if (preg_match_all('/(\d{1,2})\s*(?:человек|человека|чел|люд|челек)/u', $low, $peopleMatches) && !empty($peopleMatches[1])) {
        $facts['people'] = end($peopleMatches[1]);
    } elseif (empty($facts['people']) && ($bareNumber !== null || $wordNumber !== null) && !empty($facts['scope'])) {
        $facts['people'] = $bareNumber ?? $wordNumber;
    }

    if (preg_match_all('/(\d{1,2})\s*(?:сануз|ванн|точ(?:ек|ки|ка|к)|кран|душ)/u', $low, $bathroomMatches) && !empty($bathroomMatches[1])) {
        $facts['bathrooms'] = end($bathroomMatches[1]);
    } elseif (!empty($facts['people']) && empty($facts['bathrooms']) && ($bareNumber !== null || $wordNumber !== null)) {
        $candidate = $bareNumber ?? $wordNumber;
        if ($candidate !== ($facts['people'] ?? null)) {
            $facts['bathrooms'] = $candidate;
        }
    }

    if (preg_match('/\b([123])\s*фаз/u', $low, $phaseMatch)) {
        $n = $phaseMatch[1];
        $facts['power_phase'] = $n . ($n === '1' ? ' фаза' : ' фазы');
    }

    if (preg_match('/(?:расстояние|до дома)\D{0,15}(\d{1,4})/u', $low, $distanceMatch)) {
        $facts['distance_m'] = $distanceMatch[1];
    }

    if (
        preg_match('/(?:диаметр|диамент|диам\w*|труб[аы])\D{0,15}(\d{2,3})/u', $low, $diameterMatch) ||
        preg_match('/(\d{2,3})\s*(?:мм)?\s*(?:диаметр|диамент|диам\w*)/u', $low, $diameterMatch)
    ) {
        $facts['casing_diameter_mm'] = $diameterMatch[1];
    }

    if (($facts['task'] ?? '') === 'Скважинный насос') {
        if (
            preg_match('/(\d{1,3})\s*(?:уров\w*|уроы\w*)/u', $low, $waterLevelMatch) ||
            preg_match('/(?:уров\w*|уроы\w*)\s*(?:воды\s*)?(\d{1,3})/u', $low, $waterLevelMatch)
        ) {
            $facts['water_level_m'] = $waterLevelMatch[1];
        }

        if (contains_text($low, 'зеркало')) {
            if (
                preg_match('/(\d{1,3})\s*зеркал\w*/u', $low, $mirrorMatch) ||
                preg_match('/зеркало\s*(?:на\s*)?(\d{1,3})/u', $low, $mirrorMatch)
            ) {
                $facts['water_level_m'] = $mirrorMatch[1];
            }
        }

        if (empty($facts['water_level_m']) && preg_match('/(?:вод[аы]|вода\s+стоит|уровень\s+воды)\D{0,15}(\d{1,3})\s*(?:м|метр)/u', $low, $waterLevelNaturalMatch)) {
            $facts['water_level_m'] = $waterLevelNaturalMatch[1];
        }

        if (contains_text($low, 'глуб')) {
            if (
                preg_match('/(\d{1,3})\s*глуб\w*/u', $low, $depthMatch) ||
                preg_match('/глуб\w*\s*(?:скважины\s*)?(\d{1,3})/u', $low, $depthMatch)
            ) {
                $facts['well_depth_m'] = $depthMatch[1];
            }
        }

        if (preg_match('/скважин\w*\D{0,15}(\d{1,3})\s*(?:м|метр)/u', $low, $wellDepthNaturalMatch)) {
            $facts['well_depth_m'] = $wellDepthNaturalMatch[1];
        }

        if (empty($facts['well_depth_m']) && preg_match('/^\D*(\d{1,3})\s*(?:м|метр\w*)/u', $low, $firstMeterMatch)) {
            $facts['well_depth_m'] = $firstMeterMatch[1];
        }
    }
}

function contains_any(string $haystack, array $needles): bool
{
    foreach ($needles as $needle) {
        if (contains_text($haystack, $needle)) {
            return true;
        }
    }
    return false;
}

function contains_text(string $haystack, string $needle): bool
{
    return $needle !== '' && mb_strpos($haystack, $needle, 0, 'UTF-8') !== false;
}

function is_ready_for_handoff(array $state): bool
{
    $facts = $state['facts'];

    if (($facts['task'] ?? '') === 'Дренажный насос') {
        return !empty($facts['contact'])
            && !empty($facts['drainage_place'])
            && !empty($facts['drainage_water'])
            && !empty($facts['drainage_depth']);
    }

    if (($facts['task'] ?? '') === 'Повышение давления') {
        return !empty($facts['contact'])
            && !empty($facts['scope'])
            && (!empty($facts['people']) || !empty($facts['object_type']) || !empty($facts['usage_points']))
            && !empty($facts['bathrooms']);
    }

    return !empty($facts['contact']) && !empty($facts['water_treatment']) && count($state['messages']) >= 6;
}

function next_question(array $state): string
{
    $facts = $state['facts'];

    if (empty($facts['task'])) {
        return 'Понял. Уточните, пожалуйста, для какой задачи насос: скважина, колодец, дренаж, канализация или другая задача?';
    }

    if (($facts['task'] ?? '') === 'Дренажный насос') {
        return next_drainage_question($facts);
    }

    if (($facts['task'] ?? '') === 'Повышение давления') {
        return next_pressure_boost_question($facts);
    }

    if (empty($facts['scope'])) {
        return 'Вам нужен только насос или полный комплект: насос, кабель, труба, автоматика, защита?';
    }

    if (($facts['task'] ?? '') === 'Скважинный насос' && (empty($facts['well_depth_m']) || empty($facts['water_level_m']) || empty($facts['casing_diameter_mm']))) {
        return 'Для скважины нужны данные: глубина скважины, зеркало воды и диаметр обсадной трубы. Напишите, что известно.';
    }

    if (!empty($facts['well_depth_m']) && !empty($facts['water_level_m'])) {
        $wellDepth = (int) $facts['well_depth_m'];
        $waterLevel = (int) $facts['water_level_m'];
        if ($waterLevel > $wellDepth) {
            return 'Уточните, пожалуйста: зеркало воды не может быть глубже самой скважины. На какой глубине вода от поверхности?';
        }
    }

    if (empty($facts['people']) || empty($facts['bathrooms'])) {
        return 'Сколько человек будет пользоваться водой и сколько точек водоразбора: санузлы, кухня, душ, баня, полив?';
    }

    if (empty($facts['distance_m'])) {
        if (!empty($facts['power_phase'])) {
            return 'Понял, электричество: ' . $facts['power_phase'] . '. Какое расстояние от источника воды до дома/объекта?';
        }
        return 'Какое расстояние от источника воды до дома/объекта? Если знаете — укажите ещё этажность и напряжение 220/380 В.';
    }

    if (empty($facts['water_treatment'])) {
        return 'В конце уточню по воде: есть ли анализ воды и нужна ли водоочистка/фильтры?';
    }

    if (empty($facts['contact'])) {
        return 'Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру.';
    }

    return 'Спасибо, уточняю последние детали и готовлю заявку для менеджера.';
}

function next_pressure_boost_question(array $facts): string
{
    if (empty($facts['scope'])) {
        return 'Для повышения давления нужна насосная станция/насос с автоматикой или уже есть часть оборудования?';
    }

    if (empty($facts['people']) && empty($facts['object_type']) && empty($facts['usage_points'])) {
        return 'Для какого объекта повышаем давление: баня/дом/дача? Сколько точек водоразбора будет работать: душ, кран, туалет, полив?';
    }

    if (empty($facts['bathrooms'])) {
        return 'Понял задачу. Сколько примерно точек водоразбора будет работать: душ, кран, туалет, полив? Можно диапазоном, например 3-5.';
    }

    if (empty($facts['distance_m'])) {
        return 'Уточните, пожалуйста: где будет стоять станция и примерно какое расстояние до точек водоразбора?';
    }

    if (empty($facts['contact'])) {
        return 'Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру.';
    }

    return 'Спасибо, уточняю последние детали и готовлю заявку для менеджера.';
}

function next_drainage_question(array $facts): string
{
    if (empty($facts['drainage_place']) || empty($facts['drainage_water'])) {
        return 'Уточните по дренажному насосу: откуда нужно откачивать воду (подвал, погреб, приямок, участок) и какая вода — чистая, грязная, дождевая/ливневая?';
    }

    if (empty($facts['drainage_depth'])) {
        return 'Какая примерно глубина воды/приямка и куда нужно отводить воду: в канаву, ливнёвку, на участок?';
    }

    if (empty($facts['contact'])) {
        return 'Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру.';
    }

    return 'Спасибо, уточняю последние детали и готовлю заявку для менеджера.';
}

function append_lead(array $lead): void
{
    $payload = [
        'created_at' => gmdate('c'),
    ] + $lead;

    $line = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($line === false) {
        throw new RuntimeException('Не удалось сериализовать заявку.');
    }

    if (file_put_contents(LEADS_PATH, $line . PHP_EOL, FILE_APPEND | LOCK_EX) === false) {
        throw new RuntimeException('Не удалось сохранить заявку.');
    }
}

function extract_lead_summary(array $state): string
{
    $facts = $state['facts'];
    $lines = ['## Заявка на насосное оборудование'];
    $mapping = [
        'name' => 'Имя',
        'city' => 'Город',
        'contact' => 'Контакт',
        'task' => 'Задача',
        'scope' => 'Объём поставки',
        'object_type' => 'Объект',
        'usage_points' => 'Назначение/точки',
        'water_treatment' => 'Водоочистка/анализ воды',
        'drainage_place' => 'Место откачки',
        'drainage_water' => 'Тип воды для откачки',
        'drainage_depth' => 'Глубина воды/приямка',
        'well_depth_m' => 'Глубина скважины, м',
        'water_level_m' => 'Зеркало воды, м',
        'casing_diameter_mm' => 'Диаметр трубы, мм',
        'people' => 'Пользователей',
        'bathrooms' => 'Санузлов/ванных',
        'distance_m' => 'Расстояние до объекта, м',
        'power_phase' => 'Электричество',
    ];

    foreach ($mapping as $key => $label) {
        $value = $facts[$key] ?? null;
        if ($value !== null && $value !== '') {
            $lines[] = '- ' . $label . ': ' . $value;
        }
    }

    $lines[] = '';
    $lines[] = 'Исходные сообщения клиента:';
    $lines[] = $facts['raw_request'] ?? '—';

    return implode("\n", $lines);
}

function notify_telegram(array $config, string $summary): ?array
{
    $token = trim((string) ($config['telegram_bot_token'] ?? ''));
    $chatId = trim((string) ($config['telegram_group_chat_id'] ?? ''));
    if ($token === '' || $chatId === '') {
        return null;
    }

    $text = '<b>Новая заявка с сайта</b>' . "\n\n" . htmlspecialchars($summary, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    $url = 'https://api.telegram.org/bot' . rawurlencode($token) . '/sendMessage';
    $postFields = http_build_query([
        'chat_id' => $chatId,
        'text' => $text,
        'parse_mode' => 'HTML',
        'disable_web_page_preview' => 'true',
    ]);

    $responseBody = null;
    $httpCode = null;

    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $postFields,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 12,
            CURLOPT_CONNECTTIMEOUT => 6,
            CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        ]);
        $responseBody = curl_exec($ch);
        $httpCode = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        if ($responseBody === false) {
            $responseBody = json_encode(['ok' => false, 'description' => curl_error($ch)], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        }
        curl_close($ch);
    } else {
        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => "Content-Type: application/x-www-form-urlencoded\r\n",
                'content' => $postFields,
                'timeout' => 12,
                'ignore_errors' => true,
            ],
        ]);
        $responseBody = @file_get_contents($url, false, $context);
        if (isset($http_response_header) && is_array($http_response_header)) {
            foreach ($http_response_header as $headerLine) {
                if (preg_match('#^HTTP/\S+\s+(\d{3})#', $headerLine, $match)) {
                    $httpCode = (int) $match[1];
                    break;
                }
            }
        }
    }

    $decoded = is_string($responseBody) ? json_decode($responseBody, true) : null;
    return [
        'http_code' => $httpCode,
        'ok' => (bool) ($decoded['ok'] ?? false),
        'result' => $decoded['result'] ?? null,
        'description' => $decoded['description'] ?? null,
    ];
}
