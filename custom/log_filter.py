import logging
import re

# Master switch: set False to disable all filtering.
FILTERS_ENABLED = True

# Auto-apply when this module is imported.
AUTO_APPLY = True

LOGGER_NAMES = ["ok"]

# Rules are "drop on match".
# - enabled: toggle a single rule
# - contains: substring or list of substrings
# - regex: regex pattern or list of patterns
# - level: "INFO"/"WARNING"
# - thread: thread name (record.threadName)
# - logger: logger name (record.name)
# - startswith/endswith: string match on record.getMessage()
FILTER_RULES = [
    {
        "enabled": True,
        "name": "suppress noisy gray_book_boss warnings",
        "contains": "find_one:found gray_book_boss too many",
        "level": "WARNING",
    },
    {
        "enabled": True,
        "name": "suppress noisy gray_book_all_monsters warnings",
        "contains": "find_one:found gray_book_all_monsters too many",
        "level": "WARNING",
    },
    {
        "enabled": False,
        "name": "suppress update_pc_device start info",
        "contains": "start update_pc_device",
        "level": "INFO",
    },
    {
        "enabled": True,
        "name": "suppress BaseCombatTask info",
        "startswith": "BaseCombatTask:",
        "level": "INFO",
    },
    {
        "enabled": True,
        "name": "suppress CombatCheck error",
        "startswith": "CombatCheck:keep_boss_text_white",
        "level": "ERROR",
    },
    {
        "enabled": True,
        "name": "suppress Cartethyia combat info",
        "contains": "Cartethyia",
        "level": "INFO",
    },
]


class RuleBasedFilter(logging.Filter):
    def __init__(self, rules):
        super().__init__()
        self.rules = rules

    def filter(self, record):
        if not FILTERS_ENABLED:
            return True
        message = record.getMessage()
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            if _rule_matches(rule, record, message):
                return False
        return True


def apply_filters(logger_names=None):
    if not FILTERS_ENABLED:
        return
    names = logger_names or LOGGER_NAMES
    if isinstance(names, str):
        names = [names]
    for name in names:
        logger = logging.getLogger(name)
        if any(isinstance(f, RuleBasedFilter) for f in logger.filters):
            continue
        logger.addFilter(RuleBasedFilter(FILTER_RULES))


def remove_filters(logger_names=None):
    names = logger_names or LOGGER_NAMES
    if isinstance(names, str):
        names = [names]
    for name in names:
        logger = logging.getLogger(name)
        logger.filters = [f for f in logger.filters if not isinstance(f, RuleBasedFilter)]


def _rule_matches(rule, record, message):
    if not _match_level(rule.get("level"), record):
        return False
    if not _match_text(rule.get("logger"), record.name):
        return False
    if not _match_text(rule.get("thread"), record.threadName):
        return False
    if not _match_contains(rule.get("contains"), message):
        return False
    if not _match_regex(rule.get("regex"), message):
        return False
    if not _match_starts_ends(rule.get("startswith"), message, starts=True):
        return False
    if not _match_starts_ends(rule.get("endswith"), message, starts=False):
        return False
    return True


def _match_level(level, record):
    if level is None:
        return True
    if isinstance(level, (list, tuple, set)):
        return any(_match_level(item, record) for item in level)
    if isinstance(level, int):
        return record.levelno == level
    if isinstance(level, str):
        return record.levelname == level.upper()
    return True


def _match_text(expected, actual):
    if expected is None:
        return True
    if isinstance(expected, (list, tuple, set)):
        return actual in expected
    return actual == expected


def _match_contains(needle, message):
    if not needle:
        return True
    if isinstance(needle, (list, tuple, set)):
        return any(item in message for item in needle)
    return needle in message


def _match_regex(patterns, message):
    if not patterns:
        return True
    if isinstance(patterns, (list, tuple, set)):
        return any(re.search(pat, message) for pat in patterns)
    return re.search(patterns, message) is not None


def _match_starts_ends(expected, message, *, starts):
    if not expected:
        return True
    if isinstance(expected, (list, tuple, set)):
        if starts:
            return any(message.startswith(item) for item in expected)
        return any(message.endswith(item) for item in expected)
    if starts:
        return message.startswith(expected)
    return message.endswith(expected)


if AUTO_APPLY:
    apply_filters()
