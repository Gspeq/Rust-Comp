import type { Provider } from "./domain";
const BASE = "http://127.0.0.1:43117";
export async function fetchProviders(): Promise<Provider[]> {
  const response = await fetch(`${BASE}/api/v1/integrations`);
  if (!response.ok) throw new Error(`Integration catalog failed: ${response.status}`);
  const payload = await response.json() as { providers: Provider[] };
  return payload.providers;
}
export async function serverHealth(): Promise<boolean> {
  try { return (await fetch(`${BASE}/health`)).ok; } catch { return false; }
}
