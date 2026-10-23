import { type ChangeEvent, useEffect, useState } from 'react';
import { Activity, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { subscribeToFeatureChanges, type FeatureChangeEvent } from '../../api/featureEvents';

const EVENT_HISTORY_LIMIT = 50;
const EVENT_BUCKET_COUNT = 30;
const EVENT_BUCKET_DURATION_MS = 10_000;
const EVENT_WINDOW_DURATION_MS = EVENT_BUCKET_COUNT * EVENT_BUCKET_DURATION_MS;

type EventConnectionStatus = 'connecting' | 'connected' | 'reconnecting';

type ReceivedFeatureChange = {
  event: FeatureChangeEvent;
  receivedAt: number;
};

type HeaderEntry = {
  name: string;
  value: string;
};

type HeaderResult = {
  headers: HeaderEntry[];
  statusCode?: number;
  statusText: string;
  error?: string;
};

function defaultTargetUrl() {
  return new URL('/', window.location.origin).toString();
}

async function fetchHeaders(url: string): Promise<HeaderResult> {
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store'
    });

    return {
      headers: Array.from(response.headers.entries())
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => a.name.localeCompare(b.name)),
      statusCode: response.status,
      statusText: response.statusText
    };
  } catch (cause) {
    return {
      headers: [],
      statusText: '',
      error: cause instanceof Error ? cause.message : 'Unknown error'
    };
  }
}

function eventBuckets(arrivalTimes: number[], now: number) {
  const currentBucketStart = Math.floor(now / EVENT_BUCKET_DURATION_MS) * EVENT_BUCKET_DURATION_MS;
  const firstBucketStart = currentBucketStart - (EVENT_BUCKET_COUNT - 1) * EVENT_BUCKET_DURATION_MS;
  const counts = Array.from({ length: EVENT_BUCKET_COUNT }, () => 0);

  for (const receivedAt of arrivalTimes) {
    const index = Math.floor((receivedAt - firstBucketStart) / EVENT_BUCKET_DURATION_MS);
    if (index >= 0 && index < counts.length) {
      counts[index] += 1;
    }
  }

  return { counts, firstBucketStart, currentBucketStart };
}

function formatEventTime(timestamp: number | string) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? String(timestamp) : date.toLocaleTimeString();
}

function connectionLabel(status: EventConnectionStatus) {
  switch (status) {
    case 'connected':
      return 'Connected';
    case 'reconnecting':
      return 'Reconnecting';
    default:
      return 'Connecting';
  }
}

function connectionStatusClass(status: EventConnectionStatus) {
  switch (status) {
    case 'connected':
      return 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300';
    case 'reconnecting':
      return 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300';
    default:
      return 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300';
  }
}

function connectionDotClass(status: EventConnectionStatus) {
  switch (status) {
    case 'connected':
      return 'bg-emerald-500';
    case 'reconnecting':
      return 'bg-amber-500';
    default:
      return 'bg-sky-500';
  }
}

function operationClass(operation: string) {
  switch (operation.toLowerCase()) {
    case 'create':
    case 'insert':
      return 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300';
    case 'delete':
      return 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/60 dark:text-rose-300';
    default:
      return 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300';
  }
}

export function DebugView() {
  const [targetInput, setTargetInput] = useState(defaultTargetUrl);
  const [targetUrl, setTargetUrl] = useState(defaultTargetUrl);
  const [requestVersion, setRequestVersion] = useState(0);
  const [headers, setHeaders] = useState<HeaderEntry[]>([]);
  const [statusCode, setStatusCode] = useState<number>();
  const [statusText, setStatusText] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [eventConnectionStatus, setEventConnectionStatus] = useState<EventConnectionStatus>('connecting');
  const [receivedEvents, setReceivedEvents] = useState<ReceivedFeatureChange[]>([]);
  const [eventArrivalTimes, setEventArrivalTimes] = useState<number[]>([]);
  const [eventClock, setEventClock] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    void fetchHeaders(targetUrl).then(result => {
      if (cancelled) {
        return;
      }

      setHeaders(result.headers);
      setStatusCode(result.statusCode);
      setStatusText(result.statusText);
      setError(result.error);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [requestVersion, targetUrl]);

  useEffect(() => {
    const updateClock = window.setInterval(() => {
      const now = Date.now();
      setEventClock(now);
      setEventArrivalTimes(current => current.filter(receivedAt => receivedAt >= now - EVENT_WINDOW_DURATION_MS));
    }, EVENT_BUCKET_DURATION_MS);
    const unsubscribe = subscribeToFeatureChanges(
      event => {
        const receivedAt = Date.now();
        setEventClock(receivedAt);
        setEventArrivalTimes(current => [
          ...current.filter(timestamp => timestamp >= receivedAt - EVENT_WINDOW_DURATION_MS),
          receivedAt
        ]);
        setReceivedEvents(current => [{ event, receivedAt }, ...current].slice(0, EVENT_HISTORY_LIMIT));
      },
      {
        onOpen: () => setEventConnectionStatus('connected'),
        onError: () => setEventConnectionStatus('reconnecting')
      }
    );

    return () => {
      window.clearInterval(updateClock);
      unsubscribe();
    };
  }, []);

  const { counts: eventCounts, firstBucketStart, currentBucketStart } = eventBuckets(eventArrivalTimes, eventClock);
  const maximumEventCount = Math.max(1, ...eventCounts);
  const eventsInWindow = eventCounts.reduce((total, count) => total + count, 0);

  return (
    <section className="min-h-0 overflow-auto rounded-[min(var(--radius-4xl),24px)] border border-border bg-card shadow-sm">
      <Card className="border-0 bg-transparent shadow-none">
        <CardHeader className="border-b border-chart-2/20 bg-chart-2/5">
          <CardTitle className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-md bg-chart-2 text-white shadow-sm">
              <Activity className="size-4" />
            </span>
            Runtime diagnostics
          </CardTitle>
          <CardDescription>Inspect live feature events and browser-visible response headers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6 pt-5">
          <section
            className="space-y-4"
            aria-labelledby="feature-event-heading">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2
                  id="feature-event-heading"
                  className="flex items-center gap-2 text-sm font-semibold text-chart-2">
                  <span className="h-4 w-1 bg-chart-2" />
                  Feature events
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">Incoming changes over the last five minutes.</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={connectionStatusClass(eventConnectionStatus)}>
                  <span className={`size-1.5 rounded-full ${connectionDotClass(eventConnectionStatus)}`} />
                  {connectionLabel(eventConnectionStatus)}
                </Badge>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Clear received events"
                  title="Clear received events"
                  disabled={receivedEvents.length === 0}
                  onClick={() => {
                    setReceivedEvents([]);
                    setEventArrivalTimes([]);
                  }}>
                  <Trash2 />
                </Button>
              </div>
            </div>

            <div className="grid border-y border-border sm:grid-cols-3 sm:divide-x sm:divide-border">
              <div className="border-l-4 border-chart-2 bg-chart-2/5 px-4 py-3">
                <div className="text-xs text-muted-foreground">Five-minute total</div>
                <div className="font-mono text-2xl font-semibold tabular-nums text-chart-2">{eventsInWindow}</div>
              </div>
              <div className="border-l-4 border-chart-1 bg-chart-1/5 px-4 py-3 sm:border-l-0">
                <div className="text-xs text-muted-foreground">Retained events</div>
                <div className="font-mono text-2xl font-semibold tabular-nums text-amber-700 dark:text-amber-300">
                  {receivedEvents.length}
                </div>
              </div>
              <div className="border-l-4 border-chart-5 bg-chart-5/5 px-4 py-3 sm:border-l-0">
                <div className="text-xs text-muted-foreground">Last received</div>
                <div className="mt-1 font-mono text-sm font-semibold tabular-nums text-chart-5">
                  {receivedEvents[0] ? formatEventTime(receivedEvents[0].receivedAt) : '—'}
                </div>
              </div>
            </div>

            <div>
              <div
                className="flex h-40 items-end gap-0.5 border border-border bg-[repeating-linear-gradient(to_top,transparent_0,transparent_calc(25%-1px),var(--color-border)_25%)] px-2 pt-3"
                role="img"
                aria-label={`${eventsInWindow} feature events received in the last five minutes`}>
                {eventCounts.map((count, index) => (
                  <div
                    key={firstBucketStart + index * EVENT_BUCKET_DURATION_MS}
                    className="flex h-full min-w-0 flex-1 items-end"
                    title={`${formatEventTime(firstBucketStart + index * EVENT_BUCKET_DURATION_MS)}: ${count} event${count === 1 ? '' : 's'}`}>
                    <div
                      className={`w-full transition-[height] duration-300 ${index === eventCounts.length - 1 ? 'bg-chart-1' : 'bg-chart-2/80'}`}
                      style={{ height: count === 0 ? '1px' : `${Math.max(5, (count / maximumEventCount) * 100)}%` }}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-1 flex justify-between font-mono text-[11px] text-muted-foreground">
                <span>{formatEventTime(firstBucketStart)}</span>
                <span>{formatEventTime(currentBucketStart)}</span>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium text-foreground">Latest payloads</h3>
              {receivedEvents.length === 0 ? (
                <p className="text-sm text-muted-foreground">Waiting for feature events.</p>
              ) : (
                <div className="max-h-96 divide-y divide-border overflow-auto border-y border-border bg-background/40">
                  {receivedEvents.map(received => (
                    <details
                      key={`${received.event.id}:${received.receivedAt}`}
                      className="group border-l-2 border-chart-2 py-2 transition-colors open:bg-chart-2/5 hover:bg-muted/60">
                      <summary className="grid cursor-pointer list-none gap-1 px-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-center [&::-webkit-details-marker]:hidden">
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">
                          {formatEventTime(received.receivedAt)}
                        </span>
                        <span className="truncate font-medium">
                          {received.event.dataset} / {received.event.maplayer}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {received.event.localids.length} object{received.event.localids.length === 1 ? '' : 's'}
                        </span>
                      </summary>
                      <div className="mt-2 grid gap-2 px-3">
                        <div className="flex flex-wrap gap-1">
                          {received.event.operations.map((operation, index) => (
                            <Badge
                              key={`${operation}:${index}`}
                              variant="outline"
                              className={operationClass(operation)}>
                              {operation}
                            </Badge>
                          ))}
                        </div>
                        <pre className="overflow-auto border border-chart-2/15 bg-chart-2/5 p-3 font-mono text-[11px] leading-relaxed text-foreground">
                          {JSON.stringify(received.event, null, 2)}
                        </pre>
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </div>
          </section>
          <Separator />
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-chart-5">
              <span className="h-4 w-1 bg-chart-5" />
              Response headers
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Lists response headers visible to the browser for a fetched URL.
            </p>
          </div>
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={event => {
              event.preventDefault();
              const trimmed = targetInput.trim();
              if (!trimmed) {
                return;
              }

              setLoading(true);
              setError(undefined);
              setTargetUrl(trimmed);
              setRequestVersion(version => version + 1);
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
          <div className="grid gap-2 border-l-4 border-chart-5 bg-chart-5/5 px-4 py-3 text-sm">
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
                  className="grid gap-1 border-l-2 border-chart-5 bg-chart-5/5 px-3 py-2 transition-colors hover:bg-chart-5/10">
                  <dt className="font-mono text-xs font-semibold text-chart-5">{header.name}</dt>
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
