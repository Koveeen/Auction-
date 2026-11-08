from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Lot:
    source: str
    lot_id: str
    title: str
    description: str = ""
    grade: str = ""
    url: str = ""
    price: str = ""
    image_url: str = ""

    @property
    def text(self) -> str:
        return " ".join([self.title, self.description, self.grade]).lower()


def _grade_score(text: str) -> int | None:
    m = re.search(r"\bMS\s*([6-7]\d)\b", text.upper())
    return int(m.group(1)) if m else None


def is_candidate(lot: Lot, rules: dict[str, Any]) -> bool:
    text = lot.text
    if any(word.lower() in text for word in rules.get("exclude_keywords", [])):
        return False
    regions = rules.get("regions", [])
    denominations = rules.get("denominations", [])
    region_hit = any(word.lower() in text for word in regions)
    denom_hit = any(word.lower() in text for word in denominations)
    if not (region_hit and denom_hit):
        return False
    score = _grade_score(text)
    if score is not None:
        return score >= int(rules.get("grade_min_numeric", 60))
    return any(word.lower() in text for word in rules.get("grade_keywords", []))


def normalize_item(source: str, item: dict[str, Any]) -> Lot:
    def first(*keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    return Lot(
        source=source,
        lot_id=first("lot_id", "lotNumber", "lot", "id") or first("url"),
        title=first("title", "name", "lotTitle"),
        description=first("description", "text", "lotDescription"),
        grade=first("grade", "grading", "condition"),
        url=first("url", "lotUrl", "link"),
        price=first("currentBid", "price", "estimate"),
        image_url=first("image", "imageUrl", "thumbnail"),
    )
