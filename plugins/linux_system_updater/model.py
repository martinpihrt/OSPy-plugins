"""Pure helpers for the Linux System Updater plug-in."""

import calendar
import datetime as dt
import re


PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$")
VALID_FREQUENCIES = ("daily", "weekly", "monthly")
VALID_DELAY_UNITS = ("minutes", "hours", "days")


def parse_clock(value):
    """Return a validated (hour, minute) tuple."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or ""))
    if not match:
        raise ValueError("Invalid time")
    hour, minute = (int(item) for item in match.groups())
    if hour > 23 or minute > 59:
        raise ValueError("Invalid time")
    return hour, minute


def next_check(now, frequency, clock, weekday=0, month_day=1):
    """Calculate the next local scheduled check strictly after *now*."""
    if frequency not in VALID_FREQUENCIES:
        frequency = "daily"
    hour, minute = parse_clock(clock)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if frequency == "daily":
        if candidate <= now:
            candidate += dt.timedelta(days=1)
        return candidate

    if frequency == "weekly":
        weekday = max(0, min(6, int(weekday)))
        candidate += dt.timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= now:
            candidate += dt.timedelta(days=7)
        return candidate

    month_day = max(1, min(31, int(month_day)))
    year, month = now.year, now.month
    for _unused in range(14):
        day = min(month_day, calendar.monthrange(year, month)[1])
        candidate = now.replace(
            year=year, month=month, day=day,
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        if candidate > now:
            return candidate
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    raise ValueError("Unable to calculate next monthly check")


def delay_seconds(value, unit):
    value = max(1, min(365, int(value)))
    if unit not in VALID_DELAY_UNITS:
        unit = "hours"
    return value * {"minutes": 60, "hours": 3600, "days": 86400}[unit]


def normalize_package(value):
    value = str(value or "").strip().lower()
    return value if PACKAGE_RE.fullmatch(value) else ""


def parse_exclusions(value):
    """Parse exact Debian package names from commas or whitespace."""
    result = []
    for item in re.split(r"[\s,;]+", str(value or "")):
        package = normalize_package(item)
        if package and package not in result:
            result.append(package)
    return result


def parse_upgradable(output):
    """Parse the stable machine-relevant fields from ``apt list --upgradable``."""
    updates = []
    seen = set()
    pattern = re.compile(
        r"^(?P<name>[^/\s]+)/(?P<source>\S+)\s+(?P<candidate>\S+)\s+"
        r"(?P<arch>\S+)\s+\[upgradable from:\s*(?P<installed>[^\]]+)\]",
        re.IGNORECASE,
    )
    for raw_line in str(output or "").splitlines():
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        package = normalize_package(match.group("name"))
        if not package or package in seen:
            continue
        seen.add(package)
        source = match.group("source")
        updates.append({
            "name": package,
            "installed": match.group("installed").strip(),
            "candidate": match.group("candidate").strip(),
            "architecture": match.group("arch").strip(),
            "source": source,
            "security": "security" in source.lower(),
        })
    return sorted(updates, key=lambda item: item["name"])


def parse_simulated_packages(output):
    """Return package names that APT says it would install or upgrade."""
    packages = []
    for raw_line in str(output or "").splitlines():
        match = re.match(r"^Inst\s+(\S+)", raw_line.strip())
        package = normalize_package(match.group(1)) if match else ""
        if package and package not in packages:
            packages.append(package)
    return packages


def build_upgrade_command(available, exclusions=None, selected=None, simulate=False):
    """Build a fixed-argument APT command without accepting arbitrary input."""
    available = [normalize_package(item) for item in available]
    available = [item for item in available if item]
    excluded = set(parse_exclusions(exclusions or ""))

    if selected is not None:
        selected = normalize_package(selected)
        if not selected or selected not in available or selected in excluded:
            raise ValueError("Package is not an allowed update")
        packages = [selected]
    else:
        packages = [item for item in available if item not in excluded]
        if not packages:
            raise ValueError("No allowed packages are available")

    if selected is None and not excluded:
        command = ["apt-get"]
        if simulate:
            command.append("-s")
        command.append("upgrade")
        if not simulate:
            command.append("-y")
        return command

    command = ["apt-get"]
    if simulate:
        command.append("-s")
    command.extend(["install", "--only-upgrade"])
    if not simulate:
        command.append("-y")
    command.extend(packages)
    return command


def package_digest(updates):
    return "|".join(
        "{}={}".format(item.get("name", ""), item.get("candidate", ""))
        for item in sorted(updates, key=lambda row: row.get("name", ""))
    )


def boot_changed(previous_boot_id, current_boot_id):
    """Return true only for two valid, different Linux boot identifiers."""
    previous = str(previous_boot_id or "").strip()
    current = str(current_boot_id or "").strip()
    return bool(previous and current and previous != current)


def pending_due(pending, now):
    try:
        return bool(pending) and float(now) >= float(pending.get("execute_at") or 0)
    except (AttributeError, TypeError, ValueError):
        return False
