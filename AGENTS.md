# Project development guide

- Keep the collector read-only, local-first, and permission-tolerant.
- Do not collect command lines, environment variables, usernames, or hostnames.
- Bind the launcher to loopback and preserve the API Host and CORS restrictions.
- Treat resource correlations as possible causes, not proven root causes.
- High memory use by itself must never be described as a memory leak.
- Run Python tests, the frontend unit checks, TypeScript build, and dependency audits before release.
- Report local, Linux, CI, dependency, and deployment verification separately; do not make universal performance or security claims.
