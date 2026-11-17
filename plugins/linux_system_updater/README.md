# Linux System Updater

Linux System Updater checks and installs Debian Linux operating-system package updates from OSPy. Its managed worker and separate APT subprocess keep package work away from the irrigation scheduler and other plug-in loops. It supports daily, weekly and monthly checks, manual checks, exact package exclusions, delayed automatic installation, per-package manual installation, live browser output, SSL e-mail notices and an optional verified reboot.

## Requirements and privileges

- Debian, Ubuntu, Raspberry Pi OS or another Linux distribution with `apt` and `apt-get`.
- OSPy 3.0.354 or newer.
- Root privileges, or preconfigured non-interactive `sudo -n` access to APT and reboot operations.
- E-mail Notifications SSL when notification delivery is enabled.

The standard OSPy systemd service has no `User=` directive and therefore runs as root. On a custom unprivileged service, the plug-in fails visibly when passwordless sudo is unavailable. It never requests, receives or stores a sudo password.

## Operation

The scheduled worker executes `apt-get update`, then reads `apt list --upgradable`. User-visible package records contain only the package name, installed version, candidate version, architecture, source and a security-update hint. The page polls protected JSON status and shows a bounded live tail of command output.

All commands are fixed argument arrays and are executed without a shell. Browser input cannot supply a command. Manual package requests must exactly match a non-excluded package in the latest APT result.

Before installation the exact transaction is simulated. Existing `apt-mark hold` state is left unchanged and respected. With no plug-in exclusions, an all-package operation uses `apt-get upgrade -y`. When exclusions exist, the plug-in requests only allowed package names through `apt-get install --only-upgrade -y`; if simulation still includes an excluded package as a dependency, the operation stops without changing packages.

APT receives a 60-second dpkg lock timeout, non-interactive mode and `--force-confold`, preserving locally modified configuration files. An active package installation is never killed merely because the plug-in is disabled or reloaded.

## Automatic update delay and cancellation

When an automatic update is scheduled, its package digest and deadline are stored in the plug-in data directory. The state survives an OSPy restart. The availability e-mail includes the deadline and a link to the authenticated OSPy page. Cancellation requires an administrator session and a CSRF-protected POST; an e-mail link never changes state by itself.

Repeated checks do not resend the same availability notice unless the candidate package set changes. A separate notice is sent immediately before installation.

## E-mail integration

Linux System Updater calls the existing `try_mail()` interface from E-mail Notifications SSL. SMTP credentials and all recipients remain exclusively in the global E-mail Notifications SSL settings. This plug-in stores only whether it should send notices and its message subject.

## Restart verification

After a successful update, optional restart uses OSPy's `helpers.reboot()`. Before reboot, the plug-in stores the current Linux boot ID and update summary. On the next boot, the worker confirms that the boot ID changed and that this plug-in started inside OSPy, then sends the success message. If the e-mail plug-in is not ready yet, delivery is retried. Without automatic reboot, the page still reports `/var/run/reboot-required` and sends a normal completion notice.

## Settings

- **Enable scheduled checks**: run checks at the configured local time.
- **Check frequency**: Daily, Weekly or Monthly.
- **Day of week / day of month**: applies to the corresponding frequency. A monthly day missing from a shorter month becomes that month's last day.
- **Automatically install updates**: create a cancellable pending operation after a successful check.
- **Automatic update delay**: 1-365 minutes, hours or days.
- **Excluded packages**: exact Debian names separated by commas, spaces or new lines.
- **Restart Linux after a successful update**: reboot only after APT exits successfully.
- **Live output lines**: retain the latest 50-500 lines in memory.
- **Send notifications through E-mail Notifications SSL** and **E-mail subject**: notification controls; recipients remain global.

## Testing

The regression tests exercise scheduling, monthly edge cases, APT output parsing, exact exclusions, package-name validation, safe command construction, transaction inspection, manifest metadata and documentation. Commands that would modify Linux are mocked or tested as pure argument construction; the automated suite never runs a real update or reboot.
