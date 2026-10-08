/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow calling the FastAPI backend from Next.js
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
