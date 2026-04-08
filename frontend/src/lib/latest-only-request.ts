export interface LatestOnlyRequestGate {
  begin(): number;
  invalidate(): number;
  isCurrent(requestId: number): boolean;
}

export function createLatestOnlyRequestGate(
  initialRequestId = 0,
): LatestOnlyRequestGate {
  let currentRequestId = initialRequestId;

  return {
    begin() {
      currentRequestId += 1;
      return currentRequestId;
    },
    invalidate() {
      currentRequestId += 1;
      return currentRequestId;
    },
    isCurrent(requestId: number) {
      return requestId === currentRequestId;
    },
  };
}
