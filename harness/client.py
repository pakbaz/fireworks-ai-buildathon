"""Fireworks chat client with a disk cache, retries and cost accounting."""
import hashlib, json, os, random, time, urllib.error, urllib.request
from . import config

def _key(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

def chat(model, messages, max_tokens=1500, json_mode=True, logprobs=False, temperature=0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if model not in config.THINKING_ONLY:
        body["reasoning_effort"] = "none"
    elif config.GLM_REASONING:
        body["reasoning_effort"] = config.GLM_REASONING
    if logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = 5
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, _key(body) + ".json")
    if os.path.exists(path):
        r = json.load(open(path)); r["_cached"] = True
        return r
    delay = 2.0
    for attempt in range(10):
        t0 = time.time()
        try:
            req = urllib.request.Request(config.API_URL, data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + config.api_key(), "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=240))
            r["_latency_ms"] = int((time.time() - t0) * 1000)
            json.dump(r, open(path + ".tmp", "w")); os.replace(path + ".tmp", path)
            r["_cached"] = False
            return r
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 9:
                ra = e.headers.get("Retry-After") if e.headers else None  # Fireworks docs: honor Retry-After, else backoff with jitter
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay + random.random()
                time.sleep(min(wait, 60)); delay = min(delay * 2, 60); continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 9:
                time.sleep(delay + random.random()); delay = min(delay * 2, 60); continue
            raise

def usage_cost(model, r):
    u = r.get("usage", {}) or {}
    pin, pout = config.PRICES.get(model, (0.0, 0.0))
    ti, to = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    return ti, to, (ti * pin + to * pout) / 1e6

def content(r):
    return (r["choices"][0]["message"].get("content") or "").strip()

def parse_json(text):
    import re
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
