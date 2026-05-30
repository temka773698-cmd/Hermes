document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.nav');

  if (toggle && nav) {
    toggle.addEventListener('click', () => nav.classList.toggle('open'));
  }

  const defaultLeadEndpoints = () => {
    const host = window.location.hostname;
    const localHosts = new Set(['127.0.0.1', 'localhost']);

    if (localHosts.has(host)) {
      return ['/api/lead', '/api/lead.php'];
    }

    return ['/api/lead.php', '/api/lead'];
  };

  const tryLeadSubmit = async (payload, endpoints) => {
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const result = await response.json().catch(() => ({}));

        if ((response.status === 404 || response.status === 405) && endpoint !== endpoints[endpoints.length - 1]) {
          lastError = new Error(`Endpoint ${endpoint} недоступен (${response.status})`);
          continue;
        }

        if (!response.ok) {
          const details = result.details || {};
          const parts = [result.error || 'Не удалось отправить заявку'];
          if (details.message) parts.push(details.message);
          if (details.hint) parts.push(`Подсказка: ${details.hint}`);
          if (result.lead_id) parts.push(`ID заявки: ${result.lead_id}`);
          if (result.log_path) parts.push(`Резервный лог: ${result.log_path}`);
          throw new Error(parts.join('\n'));
        }

        return result;
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('Не удалось отправить заявку');
  };

  document.querySelectorAll('.js-lead-form').forEach((form) => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const submitButton = form.querySelector('button[type="submit"]');
      const out = form.querySelector('.form-output');
      const data = new FormData(form);
      const payload = {
        name: data.get('name') || '',
        phone: data.get('phone') || '',
        location: data.get('location') || '',
        need: data.get('need') || '',
        comment: data.get('comment') || '',
        page: window.location.pathname,
        source: window.location.href,
      };
      const endpoints = form.dataset.leadEndpoint
        ? [form.dataset.leadEndpoint]
        : defaultLeadEndpoints();

      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Отправляем...';
      }

      try {
        const result = await tryLeadSubmit(payload, endpoints);

        if (out) {
          out.hidden = false;
          const parts = [result.message || 'Заявка обработана.'];
          if (result.lead_id) {
            parts.push(`ID заявки: ${result.lead_id}`);
          }
          if (result.log_path) {
            parts.push(`Резервный лог: ${result.log_path}`);
          }
          if (result.telegram_status === 'preview') {
            parts.push('Telegram не настроен, поэтому заявка осталась в резервном логе и показан предпросмотр.');
          }
          if (result.preview) {
            parts.push('', result.preview);
          }
          out.textContent = parts.join('\n');
        }

        form.reset();
      } catch (error) {
        if (out) {
          out.hidden = false;
          out.textContent = `Ошибка:\n${error.message}`;
        }
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = 'Отправить заявку';
        }
      }
    });
  });
});
