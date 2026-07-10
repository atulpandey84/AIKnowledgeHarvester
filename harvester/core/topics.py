import re
from typing import List
from harvester.core.models import Topic

def parse_topics(filepath: str) -> List[Topic]:
    """
    Parses topics from `.topics.txt`.
    Supports priorities [High], [Medium], [Low] as section headers or prefixes.
    Supports comments starting with '#' and blank lines.
    Allows weights and categories defined in parenthesis e.g., "Artificial Intelligence (category:AI, weight:2.5)"
    or custom flags like "enabled:false".
    """
    topics: List[Topic] = []
    current_priority = "Medium"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    for line in lines:
        raw_line = line.strip()
        if not raw_line or raw_line.startswith('#'):
            continue

        # Match Priority Header like [High], [Medium], [Low]
        priority_match = re.match(r'^\[(High|Medium|Low)\]$', raw_line, re.IGNORECASE)
        if priority_match:
            current_priority = priority_match.group(1).capitalize()
            continue

        # Parse inline attributes like: Artificial Intelligence (category:AI, weight:2.5, enabled:false)
        topic_name = raw_line
        category = None
        weight = 1.0
        enabled = True

        attr_match = re.search(r'\(([^)]+)\)', raw_line)
        if attr_match:
            attrs_str = attr_match.group(1)
            topic_name = raw_line[:attr_match.start()].strip()

            # Split by comma
            pairs = [p.strip() for p in attrs_str.split(',')]
            for pair in pairs:
                if ':' in pair:
                    key, val = pair.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key == 'category':
                        category = val
                    elif key == 'weight':
                        try:
                            weight = float(val)
                        except ValueError:
                            pass
                    elif key == 'enabled':
                        enabled = val.lower() in ('true', '1', 'yes')
                else:
                    # Single word like "disabled"
                    if pair.lower() == 'disabled':
                        enabled = False
                    elif pair.lower() == 'enabled':
                        enabled = True

        # Build Topic Object
        topic = Topic(
            name=topic_name,
            priority=current_priority,
            category=category,
            weight=weight,
            enabled=enabled,
            raw_line=raw_line
        )
        topics.append(topic)

    return topics

def format_topics(topics: List[Topic]) -> str:
    """Formats list of Topic models back into topics.txt format."""
    lines = []
    by_priority = {"High": [], "Medium": [], "Low": []}
    for t in topics:
        by_priority[t.priority].append(t)

    for prio in ["High", "Medium", "Low"]:
        prio_topics = by_priority[prio]
        if not prio_topics:
            continue
        lines.append(f"[{prio}]")
        for t in prio_topics:
            attrs = []
            if t.category:
                attrs.append(f"category:{t.category}")
            if t.weight != 1.0:
                attrs.append(f"weight:{t.weight}")
            if not t.enabled:
                attrs.append("enabled:false")

            if attrs:
                lines.append(f"{t.name} ({', '.join(attrs)})")
            else:
                lines.append(t.name)
        lines.append("")
    return "\n".join(lines).strip()
