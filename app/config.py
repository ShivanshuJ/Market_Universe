"""Settings read from environment (and a local .env file). Read at call time so tests can override."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:  # empty values in .env never override the real environment
            os.environ.setdefault(k.strip(), v)


_load_dotenv()


def settings():
    g = os.environ.get
    return {
        "crustdata_key": g("CRUSTDATA_KEY", ""),
        "anthropic_key": g("ANTHROPIC_API_KEY", ""),
        "model": g("XRAY_MODEL", "claude-sonnet-5-5"),
        "budget": float(g("XRAY_BUDGET", "300")),
        "max_people": int(g("XRAY_MAX_PEOPLE", "800")),
        "window_days": int(g("XRAY_WINDOW_DAYS", "365")),
        "max_exits": int(g("XRAY_MAX_EXITS", "800")),
        "offline": g("XRAY_OFFLINE", "0") == "1",
        "crash_after": g("XRAY_CRASH_AFTER", ""),
        "db": g("XRAY_DB", str(ROOT / "data" / "xray.db")),
        "port": int(g("PORT", "8000")),
    }
