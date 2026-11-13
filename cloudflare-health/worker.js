export async function checkBackend(env) {
  const response = await fetch(env.BACKEND_HEALTH_URL, {
    signal: AbortSignal.timeout(55000),
    headers: { 'Accept': 'application/json' },
    redirect: 'error',
  });
  if (!response.ok) throw new Error(`Backend health HTTP ${response.status}`);
  const result = await response.json();
  if (result.status !== 'ok') throw new Error('Backend health response is not ok');
  console.log('Backend health OK');
}

export default {
  async scheduled(_event, env) {
    await checkBackend(env);
  },
};
