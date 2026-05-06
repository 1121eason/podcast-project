"""
Publisher independence groups.

Cross-verification counts independent groups, not raw publisher count.
Reuters + Bloomberg + WSJ all reporting the same story is one ecosystem,
not three independent confirmations.
"""

INDEPENDENT_GROUPS: dict[str, set[str]] = {
    "western_finance": {
        "Reuters",
        "Reuters Markets（路透）",
        "Bloomberg",
        "Bloomberg News（彭博）",
        "WSJ",
        "Wall Street Journal",
        "The Wall Street Journal",
        "FT",
        "Financial Times",
        "MarketWatch",
    },
    "western_general": {
        "NYT",
        "The New York Times",
        "BBC",
        "Guardian",
        "The Guardian",
        "AP",
        "AP News",
        "Le Monde",
    },
    "us_business": {
        "CNBC",
        "Business Insider",
        "Yahoo Finance",
        "Forbes",
    },
    "us_tech": {
        "TechCrunch",
        "The Verge",
        "Wired",
        "Ars Technica",
    },
    "tw_finance": {
        "鉅亨",
        "MoneyDJ 理財網",
        "經濟日報",
        "工商時報",
        "Digitimes",
        "DIGITIMES",
    },
    "tw_general": {
        "中央社",
        "天下雜誌",
        "Yahoo奇摩",
        "iThome",
    },
    "europe_general": {
        "The Economist",
        "Le Monde",
        "Deutsche Welle",
    },
    "asia_finance": {
        "Nikkei",
        "Nikkei（日經）",
        "香港經濟日報",
        "RTHK",
        "香港電台 RTHK",
        "South China Morning Post",
    },
}


def count_independent_groups(publishers: list[str]) -> int:
    if not publishers:
        return 0
    matched_groups: set[str] = set()
    unmatched_count = 0
    for publisher in publishers:
        if not publisher:
            continue
        found = False
        for group_name, members in INDEPENDENT_GROUPS.items():
            if publisher in members:
                matched_groups.add(group_name)
                found = True
                break
        if not found:
            unmatched_count += 1
    return len(matched_groups) + unmatched_count
