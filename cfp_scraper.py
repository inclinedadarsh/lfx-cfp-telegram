import dataclasses
from typing import List, Optional

import requests
from bs4 import BeautifulSoup, Tag


CFP_URL = "https://sessionize.com/linux-foundation-events?opencfs=true"


@dataclasses.dataclass
class CfpEvent:
    title: str
    link: str
    date: Optional[str]
    location: Optional[str]
    event_type: Optional[str]
    status: Optional[str]


def _text_or_none(node: Optional[Tag]) -> Optional[str]:
    if not node:
        return None
    text = node.get_text(strip=True)
    return text or None


def fetch_cfp_events(session: Optional[requests.Session] = None) -> List[CfpEvent]:
    s = session or requests.Session()
    resp = s.get(CFP_URL, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    entries = soup.select("div.c-entry")
    events: List[CfpEvent] = []

    for entry in entries:
        # Title and link
        title_tag = entry.select_one(".c-entry__title a")
        title = _text_or_none(title_tag) or ""
        href = (
            title_tag["href"].strip()
            if title_tag and title_tag.has_attr("href")
            else ""
        )
        if href and href.startswith("/"):
            link = f"https://sessionize.com{href}"
        else:
            link = href

        # Meta items
        date_val = None
        location_val = None
        type_val = None
        status_val = None

        for meta_item in entry.select("ul.c-entry__meta li.c-entry__meta-item"):
            label_text = _text_or_none(meta_item.select_one(".c-entry__meta-label"))
            value_text = _text_or_none(meta_item.select_one(".c-entry__meta-value"))
            if (
                not label_text
                and meta_item.get("class")
                and "is-info" in meta_item.get("class", [])
            ):
                # Some items hide the label and just show a value with a link
                value_text = _text_or_none(meta_item.select_one(".c-entry__meta-value"))
                status_val = value_text or status_val
                continue
            if not label_text:
                continue

            label_key = label_text.lower()
            if "date" in label_key:
                date_val = value_text or date_val
            elif "location" in label_key:
                location_val = value_text or location_val
            elif "type" in label_key:
                type_val = value_text or type_val

        events.append(
            CfpEvent(
                title=title,
                link=link,
                date=date_val,
                location=location_val,
                event_type=type_val,
                status=status_val,
            )
        )

    return events
