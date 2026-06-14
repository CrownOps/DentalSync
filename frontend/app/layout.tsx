import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "./providers";
import { AppHeader } from "@/components/AppHeader";

export const metadata: Metadata = {
  title: "CrownOps — DentalSync",
  description: "치과기공소 의뢰서 OCR 파이프라인",
  icons: { icon: "/CrownOps_logo.png" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-50 text-gray-900">
        <Providers>
          <AppHeader />
          {children}
        </Providers>
      </body>
    </html>
  );
}
