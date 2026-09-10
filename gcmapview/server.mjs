import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { createClient } from 'redis';

const distDir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist');
const indexFile = path.join(distDir, 'index.html');
const host = '0.0.0.0';
const port = Number.parseInt(process.env.PORT ?? '8080', 10);
const featureEventStreams = [
  'geocomponents.feature-events.cadastre.parcels',
  'geocomponents.feature-events.cadastre.buildings',
  'geocomponents.feature-events.fkb_bane.jernbaneplattformkant',
  'geocomponents.feature-events.fkb_bane.spormidt',
  'geocomponents.feature-events.bygning.bygning',
  'geocomponents.feature-events.bygning.bygning_omrade',
  'geocomponents.feature-events.bygning.bygning_senterlinje',
  'geocomponents.feature-events.bygning.bygning_posisjon'
];

function requireEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} must be set`);
  }
  return value;
}

const runtimeConfigSource = `window.__GCMAPVIEW_CONFIG__ = ${JSON.stringify(
  {
    gcapiApiUrl: requireEnv('GCAPI_API_URL'),
    featureEventsUrl: '/feature-events'
  },
  null,
  2
)};\n`;
const redisUrl = requireEnv('REDIS_URL');

const contentTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.jpeg', 'image/jpeg'],
  ['.jpg', 'image/jpeg'],
  ['.js', 'application/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.map', 'application/json; charset=utf-8'],
  ['.mjs', 'application/javascript; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.webp', 'image/webp'],
  ['.woff2', 'font/woff2']
]);

function contentTypeFor(filePath) {
  return contentTypes.get(path.extname(filePath).toLowerCase()) ?? 'application/octet-stream';
}

function resolveDistPath(pathname) {
  const normalizedPath = path.posix.normalize(pathname).replace(/^\/+/, '');
  if (!normalizedPath || normalizedPath === '.') {
    return null;
  }

  if (normalizedPath.startsWith('..')) {
    return null;
  }

  return path.join(distDir, ...normalizedPath.split('/'));
}

async function sendFile(req, res, filePath) {
  const fileInfo = await stat(filePath);
  const headers = {
    'Content-Length': String(fileInfo.size),
    'Content-Type': contentTypeFor(filePath)
  };

  if (path.basename(filePath) === 'index.html') {
    headers['Cache-Control'] = 'no-store';
  }

  res.writeHead(200, headers);
  if (req.method === 'HEAD') {
    res.end();
    return;
  }

  const stream = createReadStream(filePath);
  stream.on('error', error => {
    console.error(error);
    if (!res.headersSent) {
      res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Internal Server Error');
      return;
    }

    res.destroy(error);
  });
  stream.pipe(res);
}

function delay(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function streamFeatureEvents(req, res) {
  res.writeHead(200, {
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'Content-Type': 'text/event-stream; charset=utf-8',
    'X-Accel-Buffering': 'no'
  });
  res.write('retry: 2000\n\n');

  const client = createClient({ url: redisUrl });
  let closed = false;
  const close = () => {
    closed = true;
    if (client.isOpen) {
      client.destroy();
    }
  };
  req.once('aborted', close);
  res.once('close', close);

  client.on('error', error => {
    if (!closed) {
      console.error('[gcmapview] Redis feature event subscription failed', error);
    }
  });

  const streamIds = new Map();
  const heartbeat = setInterval(() => {
    if (!closed && !res.destroyed) {
      res.write(': keepalive\n\n');
    }
  }, 15_000);

  try {
    await client.connect();
    await Promise.all(
      featureEventStreams.map(async stream => {
        const latestMessages = await client.xRevRange(stream, '+', '-', { COUNT: 1 });
        streamIds.set(stream, latestMessages[0]?.id ?? '0-0');
      })
    );
    while (!closed && !res.destroyed) {
      try {
        const results = await client.xRead(
          featureEventStreams.map(key => ({ key, id: streamIds.get(key) ?? '0-0' })),
          { BLOCK: 1000 }
        );
        for (const result of results ?? []) {
          for (const message of result.messages) {
            streamIds.set(result.name, message.id);
            const event = message.message.event;
            if (event && !closed && !res.destroyed) {
              res.write(`data: ${event}\n\n`);
            }
          }
        }
      } catch (error) {
        if (closed || res.destroyed) {
          break;
        }
        console.error('[gcmapview] Could not read feature events', error);
        await delay(1000);
      }
    }
  } catch (error) {
    if (!closed && !res.destroyed) {
      console.error('[gcmapview] Feature event stream closed after Redis failure', error);
    }
  } finally {
    clearInterval(heartbeat);
    req.off('aborted', close);
    res.off('close', close);
    if (client.isOpen) {
      client.destroy();
    }
    if (!res.writableEnded) {
      res.end();
    }
  }
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, {
        Allow: 'GET, HEAD',
        'Content-Type': 'text/plain; charset=utf-8'
      });
      res.end('Method Not Allowed');
      return;
    }

    const requestUrl = new URL(req.url ?? '/', `http://${host}`);
    if (requestUrl.pathname === '/feature-events') {
      if (req.method === 'HEAD') {
        res.writeHead(405, {
          Allow: 'GET',
          'Content-Type': 'text/plain; charset=utf-8'
        });
        res.end('Method Not Allowed');
        return;
      }
      await streamFeatureEvents(req, res);
      return;
    }
    if (requestUrl.pathname === '/runtime-config.js') {
      res.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Length': String(Buffer.byteLength(runtimeConfigSource)),
        'Content-Type': 'application/javascript; charset=utf-8'
      });
      if (req.method === 'HEAD') {
        res.end();
        return;
      }

      res.end(runtimeConfigSource);
      return;
    }

    const requestedFile = resolveDistPath(requestUrl.pathname);
    if (requestedFile) {
      try {
        const fileInfo = await stat(requestedFile);
        if (fileInfo.isFile()) {
          await sendFile(req, res, requestedFile);
          return;
        }
      } catch (error) {
        if (!error || error.code !== 'ENOENT') {
          throw error;
        }
      }
    }

    await sendFile(req, res, indexFile);
  } catch (error) {
    console.error(error);
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Internal Server Error');
  }
});

server.listen(port, host, () => {
  console.log(`gcmapview listening on http://${host}:${port}`);
});
