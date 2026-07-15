# Security Policy

## Supported Versions

SimaticML Decoder is an **Alpha-status, single-maintainer** project. Only the latest release on PyPI and the `main` branch are supported:

- Latest release version (see PyPI: https://pypi.org/project/simaticml-decoder/)
- `main` branch (pre-release, development)

No long-term support (LTS) branches or backports are provided.

## Security Model

The decoder is designed to safely process untrusted SimaticML exports. Key security commitments:

### Input Boundary

- Accepts regular UTF-8 `.xml` files only; rejects direct and discovered symlinks, `.s7dcl`, `.s7res`, and other file types.
- Rejects symlinks, junctions, reparse points, and mount points during directory discovery:
  - **Windows:** Handle-anchored traversal via native NT handles; child files are opened relative to parent directory handles, never by re-resolving paths.
  - **POSIX:** File descriptor relative operations (`os.supports_dir_fd`) and `O_NOFOLLOW` flags. Platforms without these features reject directory input outright.

### Resource Limits

Enforced per-document and per-tree to prevent resource exhaustion:

- **File size:** 10 MiB per file
- **Tree cardinality:** 10,000 XML files max, 32 directory levels max
- **XML structure:** 100,000 elements max, 256 nesting levels max, 100 attributes per element max, 1 MiB text per element max
- **Networks:** 1,000 `FlgNet` networks per document max

Inputs are rejected entirely, never truncated.

### Diagnostics

Default diagnostics use:
- Stable diagnostic codes (never raw parser output)
- Basenames only (no absolute paths)
- Single-line bounded detail (no control characters)

Folding and emission failures are isolated per file so processing can continue on valid files in the same batch.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security vulnerabilities privately via GitHub's security advisory form:

https://github.com/Czarnak/simaticml-decoder/security/advisories/new

Provide:
- Description of the vulnerability
- Steps to reproduce (if applicable)
- Potential impact

### Response Expectation

As a solo-maintained Alpha project, there is no formal SLA. However, the maintainer will:
- Confirm receipt and triage within a reasonable timeframe
- Provide a fix or mitigation plan for confirmed vulnerabilities
- Credit you in the fix commit if desired

---

For general questions about security, open an issue on GitHub (not a security advisory).
