import type { NextConfig } from "next";

// Brauzer faqat shu origin bilan gaplashadi: /api/* Business API’ga proksi qilinadi
// (cookie va CSRF same-origin, TZ 13.12). Next.js serverida biznes mantiq yo‘q.
const businessApi = process.env.BUSINESS_API_URL ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${businessApi}/api/:path*` }];
  },
  poweredByHeader: false,
};

export default nextConfig;
