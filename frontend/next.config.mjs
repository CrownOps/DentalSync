/** @type {import('next').NextConfig} */

// 로컬 풀스택 개발 편의: BACKEND_PROXY_ORIGIN 이 설정되면 Next dev 서버가
// /api/* 와 /health 를 백엔드로 프록시한다(동일 출처 → CORS·프록시 우회).
// 미설정(운영)이면 아무 영향 없음 — 프론트는 NEXT_PUBLIC_API_BASE_URL 로 직접 호출.
const backendOrigin = process.env.BACKEND_PROXY_ORIGIN;

const nextConfig = {
  // ESLint 미설정 환경에서도 build 가 멈추지 않도록 (타입 체크는 유지).
  eslint: { ignoreDuringBuilds: true },
  ...(backendOrigin
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
            { source: "/health", destination: `${backendOrigin}/health` },
          ];
        },
      }
    : {}),
};

export default nextConfig;
