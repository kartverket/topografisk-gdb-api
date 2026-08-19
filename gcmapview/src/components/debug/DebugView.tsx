import { type ChangeEvent, useEffect, useState } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

type HeaderEntry = {
  name: string;
  value: string;
};

function defaultTargetUrl() {
  return new URL('/', window.location.origin).toString();
}

export function DebugView() {
  const [targetInput, setTargetInput] = useState(defaultTargetUrl);
  const [targetUrl, setTargetUrl] = useState(defaultTargetUrl);
  const [headers, setHeaders] = useState<HeaderEntry[]>([]);
  const [statusCode, setStatusCode] = useState<number>();
  const [statusText, setStatusText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  async function loadHeaders(url: string) {
    setLoading(true);
    setError(undefined);

    try {
      const response = await fetch(url, {
        method: 'GET',
        cache: 'no-store'
      });

      const nextHeaders = Array.from(response.headers.entries())
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => a.name.localeCompare(b.name));

      setHeaders(nextHeaders);
      setStatusCode(response.status);
      setStatusText(response.statusText);
    } catch (cause) {
      setHeaders([]);
      setStatusCode(undefined);
      setStatusText('');
      setError(cause instanceof Error ? cause.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHeaders(targetUrl);
  }, [targetUrl]);

  return (
    <section className="min-h-0 overflow-auto rounded-[min(var(--radius-4xl),24px)] border border-border bg-card shadow-sm">
      <Card className="border-0 bg-transparent shadow-none">
        <CardHeader>
          <CardTitle>Debug headers</CardTitle>
          <CardDescription>Lists response headers visible to the browser for a fetched URL.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={event => {
              event.preventDefault();
              const trimmed = targetInput.trim();
              if (!trimmed) {
                return;
              }

              setTargetUrl(trimmed);
            }}>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
              value={targetInput}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTargetInput(event.target.value)}
              placeholder="https://example.test/"
              aria-label="Debug target URL"
            />
            <Button
              type="submit"
              disabled={loading}>
              <RefreshCw data-icon="inline-start" />
              {loading ? 'Loading…' : 'Reload'}
            </Button>
          </form>
          <p className="text-sm text-muted-foreground">
            The browser can reliably expose response headers here. Implicit request headers are not fully available to
            frontend JavaScript.
          </p>
          <Separator />
          {error ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Could not load headers</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-2 text-sm">
            <div className="flex flex-wrap items-center gap-3 text-muted-foreground">
              <span className="font-medium text-foreground">Target</span>
              <span className="font-mono text-xs">{targetUrl}</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-muted-foreground">
              <span className="font-medium text-foreground">Status</span>
              <span className="font-mono text-xs">
                {statusCode === undefined ? '—' : `${statusCode} ${statusText}`.trim()}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-muted-foreground">
              <span className="font-medium text-foreground">Header count</span>
              <span className="font-mono text-xs">{headers.length}</span>
            </div>
          </div>
          <Separator />
          {headers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No response headers were exposed for this request.</p>
          ) : (
            <dl className="grid gap-3 text-sm">
              {headers.map(header => (
                <div
                  key={header.name}
                  className="grid gap-1 rounded-lg border border-border/70 bg-background/60 px-3 py-2">
                  <dt className="font-mono text-xs text-muted-foreground">{header.name}</dt>
                  <dd className="m-0 break-all font-mono text-[12px] text-foreground">{header.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
