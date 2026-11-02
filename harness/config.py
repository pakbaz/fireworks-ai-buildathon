import os

# Models (verified live on the team account, 2:00 PM Nov 2 2026). Swap HARNESS_MODEL to try a stronger model.
FRONTIER_MODEL = os.environ.get("FRONTIER_MODEL", "accounts/fireworks/models/kimi-k3")
HARNESS_MODEL = os.environ.get("HARNESS_MODEL", "accounts/fireworks/models/glm-5p3-flash")

# Serverless Standard prices, USD per 1M tokens (input, output), from docs.fireworks.ai/serverless/pricing.
PRICES = {
    "accounts/fireworks/models/kimi-k3": (3.00, 15.00),
    "accounts/fireworks/models/glm-5p3-flash": (0.15, 0.50),
}

# Models that cannot turn reasoning off (verified): never send reasoning_effort to them.
THINKING_ONLY = {"accounts/fireworks/models/glm-5p3-flash"}

API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "runs", "cache")
RUNS_DIR = os.path.join(REPO, "runs")
DATA_DIR = os.path.join(REPO, "data")

ROWS = {
    "kimi_alone": dict(kind="alone", model=FRONTIER_MODEL),
    "glm_alone": dict(kind="alone", model=HARNESS_MODEL),
    "glm_harness": dict(kind="harness", model=HARNESS_MODEL, wiki=False),
    "glm_harness_wiki": dict(kind="harness", model=HARNESS_MODEL, wiki=True),
}


def api_key():
    k = os.environ.get("FIREWORKS_API_KEY")
    if not k:
        # Local, git-ignored .env next to the repo or inside it.
        for p in (os.path.join(REPO, ".env"), os.path.join(os.path.dirname(REPO), ".env")):
            if os.path.exists(p):
                for line in open(p):
                    if line.startswith("FIREWORKS_API_KEY="):
                        k = line.split("=", 1)[1].strip()
    if not k:
        raise SystemExit("Set FIREWORKS_API_KEY (or put it in a git-ignored .env).")
    return k
