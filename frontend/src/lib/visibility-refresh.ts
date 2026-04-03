export const STOCK_POLL_INTERVAL_MS = 300000;
export const VISIBILITY_REFRESH_COOLDOWN_MS = 60000;

interface VisibilityRefreshInput {
  now: number;
  lastRequestStartedAt: number | null;
  inFlight: boolean;
  cooldownMs?: number;
}

export function canRefreshOnVisibility(input: VisibilityRefreshInput): boolean {
  if (input.inFlight) {
    return false;
  }

  if (input.lastRequestStartedAt === null) {
    return true;
  }

  const cooldownMs = input.cooldownMs ?? VISIBILITY_REFRESH_COOLDOWN_MS;
  return input.now - input.lastRequestStartedAt >= cooldownMs;
}

