/**
 * DataMind — Landing Page (Day 1 skeleton)
 * Full dashboard UI implementation: Days 15-17 (EPIC 3)
 */
export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">DataMind</h1>
        <p className="text-xl text-muted-foreground">
          AI-Native Data Analytics &amp; Digital Labor Platform
        </p>
        <p className="text-sm text-muted-foreground">
          Day 1 — Foundation scaffold. Dashboard coming in Sprint 7.
        </p>
        <div className="flex gap-4 justify-center mt-8">
          <a
            href="/api-docs"
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:opacity-90"
          >
            API Docs
          </a>
          <a
            href="http://localhost:3001"
            className="px-4 py-2 border rounded-md hover:bg-accent"
            target="_blank"
            rel="noopener noreferrer"
          >
            Langfuse
          </a>
          <a
            href="http://localhost:3002"
            className="px-4 py-2 border rounded-md hover:bg-accent"
            target="_blank"
            rel="noopener noreferrer"
          >
            Grafana
          </a>
        </div>
      </div>
    </main>
  );
}
