from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "config.toml").open("rb") as stream:
    CONFIG = tomllib.load(stream)
INPUT = (ROOT / CONFIG["catalog"]["directory"]).resolve()
