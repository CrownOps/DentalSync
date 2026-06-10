/** @type {import('next').NextConfig} */
const nextConfig = {
  // ESLint 미설정 환경에서도 build 가 멈추지 않도록 (타입 체크는 유지).
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
