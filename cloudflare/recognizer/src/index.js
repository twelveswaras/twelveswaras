/**
 * twelveswaras recognizer, hosted as a Cloudflare Container.
 *
 * This worker is a thin front for a single warm container instance running the FastAPI recognizer
 * (space/api.py, the same app the Hugging Face Space ran). It forwards every request to the
 * container's port 7860, so /identify, /health and /docs all work unchanged. The container scales
 * to zero when idle and wakes on the next request; the FastAPI app already sets permissive CORS,
 * so both the gateway worker (server-to-server) and a direct browser test (?api=) work.
 */
import { Container, getContainer } from '@cloudflare/containers';

export class Recognizer extends Container {
  defaultPort = 7860;      // uvicorn api:app --port 7860 (see Dockerfile)
  sleepAfter = '5m';       // scale to zero 5 min after the last request; wake is fast on the next
}

export default {
  async fetch(request, env) {
    // One shared instance (fixed id) so the model stays warm and is reused across requests, rather
    // than cold-starting a new container per session. The FastAPI app handles concurrency itself.
    return getContainer(env.RECOGNIZER, 'recognizer').fetch(request);
  },
};
