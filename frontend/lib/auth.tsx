"use client";

// 기공소 로컬 인증 컨텍스트 (Phase 1)
// 로그인 결과 { labId, name, code } 를 localStorage 에 보관한다. lab_id(내부 PK)는
// 이후 모든 동작(업로드·조회)에 자동 사용되어, 사용자가 숫자 ID 를 직접 입력하지 않는다.
// 세션/JWT 발급은 Phase 2.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { LabAuthResponse } from "@/lib/api";

const STORAGE_KEY = "dentalsync.lab";

export interface LabSession {
  labId: number;
  name: string;
  code: string;
}

interface LabAuthContextValue {
  lab: LabSession | null;
  hydrated: boolean; // localStorage 로드 완료 여부 (SSR/초기 렌더 가드)
  login: (data: LabAuthResponse) => void;
  logout: () => void;
}

const LabAuthContext = createContext<LabAuthContextValue | null>(null);

export function LabAuthProvider({ children }: { children: ReactNode }) {
  const [lab, setLab] = useState<LabSession | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setLab(JSON.parse(raw) as LabSession);
    } catch {
      // 손상된 값은 무시
    }
    setHydrated(true);
  }, []);

  const login = (data: LabAuthResponse) => {
    const session: LabSession = {
      labId: data.lab_id,
      name: data.name,
      code: data.code,
    };
    setLab(session);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  };

  const logout = () => {
    setLab(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <LabAuthContext.Provider value={{ lab, hydrated, login, logout }}>
      {children}
    </LabAuthContext.Provider>
  );
}

export function useLabAuth(): LabAuthContextValue {
  const ctx = useContext(LabAuthContext);
  if (ctx === null) {
    throw new Error("useLabAuth must be used within LabAuthProvider");
  }
  return ctx;
}
