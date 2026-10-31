import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against their own servers and database, on ports 8001
// and 3001, so they never touch the development servers or clinic.db.
const backendDir = path.resolve(__dirname, "../backend");
const python = process.platform === "win32" ? ".venv\\Scripts\\python" : ".venv/bin/python";
const e2eDatabase = `sqlite:///${path.join(backendDir, "e2e.db").replaceAll("\\", "/")}`;

export default defineConfig({
  testDir: "./e2e",
  workers: 1, // the flows share one seeded database
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://localhost:3001",
    viewport: { width: 1440, height: 900 },
    locale: "en-AU",
  },
  webServer: [
    {
      // Fresh demo data on every run, then the API.
      command: `${python} -m app.seed && ${python} -m uvicorn app.main:app --port 8001`,
      cwd: backendDir,
      url: "http://localhost:8001/api/health",
      env: { DATABASE_URL: e2eDatabase, FRONTEND_ORIGIN: "http://localhost:3001", GEMINI_API_KEY: "" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx next build && npx next start --port 3001",
      url: "http://localhost:3001",
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8001", NEXT_DIST_DIR: ".next-e2e" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
