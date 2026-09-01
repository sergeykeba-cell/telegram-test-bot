# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not open a public GitHub issue**.

Instead, report it privately by emailing **[email protected]** with:

- A description of the vulnerability and its potential impact
- Steps to reproduce it
- Any relevant logs, screenshots, or proof-of-concept code

You should receive an acknowledgement within **72 hours**. We will keep you informed of progress toward a fix and public disclosure.

## Scope

This project is a Telegram bot + Mini App framework for conducting session-based questionnaires. Because deployments of this framework may handle sensitive respondent data (depending on how the operator configures it), we treat the following as in scope:

- Authentication/authorization bypass in the bot or Mini App
- Exposure of session tokens, respondent answers, or PDF reports to unauthorized parties
- SQL injection or other database-layer vulnerabilities
- Any way to access another user's session data via token guessing/enumeration
- Secrets (bot tokens, database credentials) leaking through logs, generated files, or git history

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Disclosure Policy

We ask that you give us a reasonable amount of time to address the issue before any public disclosure. We will credit reporters (with permission) once a fix is released.
