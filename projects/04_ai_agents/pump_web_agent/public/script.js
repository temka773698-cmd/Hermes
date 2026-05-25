const messages = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
let sessionId = localStorage.getItem('pump_agent_session_id') || null;

function addMessage(role, text) {
  const item = document.createElement('div');
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

async function sendMessage(text = '') {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message: text })
  });

  if (!response.ok) {
    throw new Error(`Ошибка сервера: ${response.status}`);
  }

  const data = await response.json();
  sessionId = data.session_id;
  localStorage.setItem('pump_agent_session_id', sessionId);
  addMessage('bot', data.reply || 'Нет ответа');
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  addMessage('user', text);
  input.value = '';
  input.disabled = true;
  form.querySelector('button').disabled = true;

  try {
    await sendMessage(text);
  } catch (error) {
    addMessage('bot', `Не получилось отправить сообщение. ${error.message}`);
  } finally {
    input.disabled = false;
    form.querySelector('button').disabled = false;
    input.focus();
  }
});

sendMessage().catch((error) => {
  addMessage('bot', `Не получилось запустить чат. ${error.message}`);
});
