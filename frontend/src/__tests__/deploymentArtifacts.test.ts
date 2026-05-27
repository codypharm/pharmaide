import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const frontendRoot = process.cwd();

describe("frontend deployment artifacts", () => {
  it("keeps the static container Cloud Run compatible", () => {
    const dockerfile = readFileSync(resolve(frontendRoot, "Dockerfile"), "utf8");

    expect(dockerfile).toContain("FROM node:24-alpine AS builder");
    expect(dockerfile).toContain("RUN npm ci");
    expect(dockerfile).toContain("RUN npm run build");
    expect(dockerfile).toContain("FROM nginxinc/nginx-unprivileged:1.29-alpine");
    expect(dockerfile).toContain("EXPOSE 8080");
    expect(dockerfile).toContain("ARG VITE_API_BASE_URL");
    expect(dockerfile).not.toContain("COPY . .");
  });

  it("serves client-side routes through the SPA fallback", () => {
    const nginxConfig = readFileSync(resolve(frontendRoot, "nginx.conf"), "utf8");

    expect(nginxConfig).toContain("listen 8080");
    expect(nginxConfig).toContain("try_files $uri $uri/ /index.html");
    expect(nginxConfig).toContain('Cache-Control "public, max-age=31536000, immutable"');
  });

  it("keeps local state and secrets out of the image context", () => {
    const dockerignore = readFileSync(resolve(frontendRoot, ".dockerignore"), "utf8").split(
      "\n",
    );

    expect(dockerignore).toContain(".env");
    expect(dockerignore).toContain(".env.*");
    expect(dockerignore).toContain("!.env.example");
    expect(dockerignore).toContain("node_modules");
    expect(dockerignore).toContain("dist");
  });
});
