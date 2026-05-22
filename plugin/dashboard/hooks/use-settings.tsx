"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  ReactNode,
} from "react";

interface SettingsContextValue {
  reflexioUrl: string;
  setReflexioUrl: (url: string) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

// Fallback only — used when ~/.reflexio/.env has no REFLEXIO_URL and the
// /api/config probe fails to return one. The source of truth is the env file.
const FALLBACK_URL = "http://localhost:8071";

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [reflexioUrl, setReflexioUrlState] = useState<string>("");
  // Once the user edits the input in this session, stop syncing from .env so
  // the override holds until page refresh.
  const overriddenRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/config", { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled && !overriddenRef.current) {
            setReflexioUrlState(FALLBACK_URL);
          }
          return;
        }
        const config = (await res.json()) as { REFLEXIO_URL?: string };
        if (cancelled || overriddenRef.current) return;
        const fromEnv = (config.REFLEXIO_URL ?? "").trim();
        setReflexioUrlState(fromEnv || FALLBACK_URL);
      } catch {
        if (!cancelled && !overriddenRef.current) {
          setReflexioUrlState(FALLBACK_URL);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setReflexioUrl = useCallback((url: string) => {
    overriddenRef.current = true;
    setReflexioUrlState(url);
  }, []);

  return (
    <SettingsContext.Provider value={{ reflexioUrl, setReflexioUrl }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
