/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output keeps the production Docker image lean - only the
  // traced node_modules subset needed at runtime is copied in, not the
  // full dependency tree used at build time.
  output: 'standalone',
  reactStrictMode: true,
};

export default nextConfig;
