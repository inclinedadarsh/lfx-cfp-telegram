import dataclasses
from typing import List, Optional, Tuple

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


@dataclasses.dataclass
class CfpEventDetails:
    title: Optional[str]
    event_starts: Optional[str]
    event_ends: Optional[str]
    location: Optional[str]
    cfp_opens: Optional[str]
    cfp_closes: Optional[str]
    cfp_timezone: Optional[str]
    cfp_notifications: Optional[str]
    schedule_announced: Optional[str]


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


def _find_ibox_by_header(
    soup: BeautifulSoup, header_tag: str, header_text: str
) -> Optional[Tag]:
    # Find an ibox where the given header contains header_text (case-insensitive)
    for ibox in soup.select("div.ibox"):
        header = ibox.select_one(f".ibox-title {header_tag}")
        if header and header_text.lower() in header.get_text(strip=True).lower():
            return ibox
    return None


def _extract_title_date_location(
    ibox: Tag,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    title_tag = ibox.select_one(".ibox-title h4")
    title = _text_or_none(title_tag)

    # Dates
    start = None
    end = None
    for col in ibox.select(
        ".ibox-content .row .col-sm-6, .ibox-content .row .col-sm-12"
    ):
        label = _text_or_none(col.select_one(".font-bold")) or ""
        value = _text_or_none(col.select_one("h2"))
        label_l = label.lower()
        if "event starts" in label_l:
            start = value
        elif "event ends" in label_l:
            end = value

    # Location: sometimes in a col-sm-12 with two span.block inside
    location_tag = None
    for col in ibox.select(".ibox-content .row .col-sm-12"):
        label = _text_or_none(col.select_one(".font-bold")) or ""
        if "location" in label.lower():
            blocks = col.select("h2 .block") or []
            if blocks:
                # Usually the last block has the printable location
                location_tag = blocks[-1]
            else:
                location_tag = col.select_one("h2")
            break
    location = _text_or_none(location_tag)

    return title, start, end, location


def _extract_cfp_section(
    ibox: Tag,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    # Opens/closes dates appear as H2s in two columns
    opens = None
    closes = None
    for col in ibox.select(".ibox-content .row .col-sm-6"):
        label = _text_or_none(col.select_one(".font-bold")) or ""
        val = _text_or_none(col.select_one("h2"))
        if "call opens" in label.lower():
            opens = val
        elif "call closes" in label.lower():
            closes = val

    # Timezone note below the dates section
    tz_small = ibox.select_one(".ibox-content .row .col-sm-12 small.text-muted")
    timezone = None
    if tz_small:
        # Try to extract the bold timezone text
        tz_b = tz_small.select_one("strong")
        timezone = _text_or_none(tz_b) or _text_or_none(tz_small)

    # Dates to remember list parsing
    notifications = None
    schedule = None
    for li in ibox.select(".ibox-content ul li"):
        text = li.get_text(" ", strip=True)
        low = text.lower()
        if low.startswith("cfp notifications") or "notifications" in low:
            # e.g., "CFP Notifications: Monday, 8 December"
            notifications = text.split(":", 1)[-1].strip()
        elif low.startswith("schedule announced") or "schedule announced" in low:
            schedule = text.split(":", 1)[-1].strip()

    return opens, closes, timezone, notifications, schedule


def fetch_event_details(
    url: str, session: Optional[requests.Session] = None
) -> CfpEventDetails:
    s = session or requests.Session()
    resp = s.get(url, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    event_box = _find_ibox_by_header(soup, "h4", "")
    # More specific: find the ibox with big title h4 (event name). If not found, fallback to first ibox
    if not event_box:
        iboxes = soup.select("div.ibox")
        event_box = iboxes[0] if iboxes else None

    title = None
    start = None
    end = None
    location = None
    if event_box:
        title_tag = event_box.select_one(".ibox-title h4")
        title = _text_or_none(title_tag)
        # Extract dates and location from content
        # Use dedicated helper to be lenient
        _title, start, end, location = _extract_title_date_location(event_box)
        title = title or _title

    cfp_box = _find_ibox_by_header(soup, "h5", "Call for Papers")
    opens = None
    closes = None
    timezone = None
    notifications = None
    schedule = None
    if cfp_box:
        opens, closes, timezone, notifications, schedule = _extract_cfp_section(cfp_box)

    return CfpEventDetails(
        title=title,
        event_starts=start,
        event_ends=end,
        location=location,
        cfp_opens=opens,
        cfp_closes=closes,
        cfp_timezone=timezone,
        cfp_notifications=notifications,
        schedule_announced=schedule,
    )
