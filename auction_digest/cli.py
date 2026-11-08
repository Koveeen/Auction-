from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import yaml

from .core import Lot, is_candidate, normalize_item

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.yaml"
DB = ROOT / "digest.sqlite3"


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text())


def init_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS lots (source TEXT, lot_id TEXT, payload TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(source, lot_id))")
    con.commit()
    return con


async def run_actor(actor: str, actor_input: dict[str, Any]) -> list[dict[str, Any]]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is not set")
    url = f"https://api.apify.com/v2/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(url, params={"token": token}, json=actor_input)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else data.get("items", [])


def save_new(con: sqlite3.Connection, lot: Lot) -> bool:
    cur = con.execute("INSERT OR IGNORE INTO lots(source, lot_id, payload) VALUES (?, ?, ?)", (lot.source, lot.lot_id, json.dumps(lot.__dict__, ensure_ascii=False)))
    con.commit()
    return cur.rowcount == 1


async def telegram_send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(text)
        return
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False})


async def main(dry_run: bool = False) -> None:
    config = load_config()
    con = init_db()
    selected: list[Lot] = []
    for source in config["sources"]:
        if not source.get("enabled"):
            continue
        items = await run_actor(source["actor"], source.get("input", {})) if not dry_run else []
        for item in items:
            lot = normalize_item(source["id"], item)
            if lot.lot_id and is_candidate(lot, config["rules"]) and save_new(con, lot):
                selected.append(lot)
    if selected:
        lines = ["Новые подходящие лоты", ""]
        for lot in selected[: config["digest"].get("max_items", 50)]:
            lines.append(f"{lot.source} · {lot.lot_id} · {lot.title}\n{lot.grade} · {lot.price}\n{lot.url}")
        await telegram_send("\n\n".join(lines))
    elif dry_run:
        print("Dry run: конфигурация загружена, запрос к Apify не выполнялся.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
