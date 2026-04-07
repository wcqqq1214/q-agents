"use client";

import {
  createContext,
  useContext,
  useCallback,
  useLayoutEffect,
  useState,
  useTransition,
} from "react";
import {
  TREND_COLOR_KEY,
  TREND_COLOR_CN_CLASS,
  type TrendMode,
} from "@/lib/trend-color-constants";

interface TrendColorContextValue {
  trendMode: TrendMode;
  setTrendMode: (mode: TrendMode) => void;
  isMounted: boolean;
}

const TrendColorContext = createContext<TrendColorContextValue>({
  trendMode: "western",
  setTrendMode: () => {},
  isMounted: false,
});

export function TrendColorProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [trendMode, setTrendModeState] = useState<TrendMode>("western");
  const [isMounted, setIsMountedState] = useState(false);
  const [, startTransition] = useTransition();

  const setTrendMode = useCallback((mode: TrendMode) => {
    setTrendModeState(mode);
    localStorage.setItem(TREND_COLOR_KEY, mode);
    if (mode === "chinese") {
      document.documentElement.classList.add(TREND_COLOR_CN_CLASS);
    } else {
      document.documentElement.classList.remove(TREND_COLOR_CN_CLASS);
    }
  }, []);

  useLayoutEffect(() => {
    const stored = localStorage.getItem(TREND_COLOR_KEY) as TrendMode | null;
    const mode =
      stored === "chinese" || stored === "western" ? stored : "western";

    if (mode === "chinese") {
      document.documentElement.classList.add(TREND_COLOR_CN_CLASS);
    }

    startTransition(() => {
      setTrendModeState(mode);
      setIsMountedState(true);
    });
  }, []);

  return (
    <TrendColorContext.Provider value={{ trendMode, setTrendMode, isMounted }}>
      {children}
    </TrendColorContext.Provider>
  );
}

export function useTrendColor() {
  return useContext(TrendColorContext);
}
