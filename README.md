# Watchtower

A small, production-style **web monitoring pipeline**: collect data from websites and APIs on a schedule, keep its full history, detect changes and send alerts.

> 🚧 Work in progress. See [ARCHITECTURE.md](ARCHITECTURE.md) for the design.

## Quick start

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
watchtower run          # fetch every source in config.yaml once
watchtower sources      # list available source types
pytest                  # tests run offline against recorded fixtures
```
