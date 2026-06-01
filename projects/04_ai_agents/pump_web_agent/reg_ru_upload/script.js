const messages = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const submitButton = form.querySelector('button');
const API_URL = './api/chat.php';
const SESSION_KEY = 'pump_agent_session_id';
let sessionId = localStorage.getItem(SESSION_KEY) || null;

function addMessage(role, text) {
  const item = document.createElement('div');
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function typingDelayFor(text) {
  const baseDelay = 450;
  const perCharDelay = 10;
  const maxDelay = 1400;
  return Math.min(maxDelay, baseDelay + String(text || '').length * perCharDelay);
}

async function postJson(url, payload, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`Ошибка сервера: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('сервер не ответил вовремя');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function sendMessage(text = '') {
  const data = await postJson(API_URL, { session_id: sessionId, message: text });

  if (!data.session_id) {
    throw new Error('не получен session_id');
  }

  sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, sessionId);

  const typing = addMessage('bot typing', 'печатает…');
  await wait(typingDelayFor(data.reply));
  typing.remove();
  addMessage('bot', data.reply || 'Нет ответа');
}

function setFormEnabled(enabled) {
  input.disabled = !enabled;
  submitButton.disabled = !enabled;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  addMessage('user', text);
  input.value = '';
  setFormEnabled(false);

  try {
    await sendMessage(text);
  } catch (error) {
    addMessage('bot', `Не получилось отправить сообщение: ${error.message}`);
  } finally {
    setFormEnabled(true);
    input.focus();
  }
});

sendMessage().catch((error) => {
  addMessage('bot', `Не получилось запустить чат: ${error.message}`);
});
