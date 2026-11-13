export async function checkBackend(env) {
  const response = await fetch(env.BACKEND_HEALTH_URL, {
    signal: AbortSignal.timeout(30000),
    headers: { 'Accept': 'application/json' },
    redirect: 'error',
  });
  if (!response.ok) throw new Error(`Backend health HTTP ${response.status}`);
  const result = await response.json();
  if (result.status !== 'ok') throw new Error('Backend health response is not ok');
  console.log('Backend health OK');
}

export class BackendHealthMonitor extends DurableObject {
  async ensureStarted() {
    // The cron is only a watchdog: it must not reset an existing alarm.
    if (await this.ctx.storage.getAlarm() === null) {
      await this.ctx.storage.setAlarm(Date.now());
    }
  }

  async alarm() {
    const startedAt = Date.now();
    try {
      await checkBackend(this.env);
      await this.ctx.storage.put('lastCheck', { at: startedAt, healthy: true });
    } catch (error) {
      console.error('Backend health failed', String(error));
      await this.ctx.storage.put('lastCheck', { at: startedAt, healthy: false });
    } finally {
      // Continue even after network failures. Avoid a rapid catch-up loop if
      // an invocation takes longer than its intended interval.
      await this.ctx.storage.setAlarm(Math.max(startedAt + INTERVAL_MS, Date.now() + 1000));
    }
  }
}

export default {
  async scheduled(_event, env) {
    await env.HEALTH_MONITOR.getByName('backend').ensureStarted();
  },
};
import { DurableObject } from 'cloudflare:workers';

const INTERVAL_MS = 40000;

