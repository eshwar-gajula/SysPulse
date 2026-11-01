# Security policy

SysPulse is a local, read-only system monitor. It is not designed to be exposed to a network. The included launcher binds to `127.0.0.1`, the data directory and SQLite file are private on Linux, and the API does not accept commands, process signals, configuration changes, credentials, or file paths.

## Data handling

SysPulse stores timestamped resource samples, findings, and a bounded list of process names, IDs, creation times, CPU percentages, RSS, and state. It does not collect process command lines, environment variables, user names, hostnames, network payloads, or credentials. No telemetry is sent. JSON and HTML reports contain diagnostic samples and should be treated as potentially sensitive when shared.

The default history is retained for 24 hours. The limit can be raised to 168 hours. On Linux, the application sets the data directory to `0700` and the database to `0600`. Backups and report downloads are the user's responsibility.

## Reporting a vulnerability

Please use GitHub's **Report a vulnerability** flow for this repository. Include the affected version, reproduction steps, and impact. Do not attach real system reports or personal process data. A fix and a supported release will be prepared before public disclosure when practical.

## Deployment boundary

Do not expose the unauthenticated API beyond loopback. Do not run the development server in a public environment. SysPulse has not been security-certified, fuzzed, or penetration-tested, and dependency advisory checks cannot prove that the application has no vulnerabilities.
