# Contributing

Thanks for your interest in contributing to this project!

## Getting started

1. Fork the repository and clone your fork
2. Create a virtual environment and install dependencies:

```bash
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your own bot token / database credentials for local testing
4. Create a branch for your change:

```bash
   git checkout -b feature/short-description
```

## Making changes

- Keep pull requests focused — one logical change per PR is easier to review than a large mixed one
- Follow the existing code style; this project uses [ruff](https://docs.astral.sh/ruff/) for linting and [mypy](https://mypy-lang.org/) for type checking (see CI workflow)
- Add or update tests for any behavior change where practical
- Update `README.md` / `README.uk.md` / `DEPLOYMENT.md` if your change affects setup, configuration, or usage

## Before opening a pull request

Run the same checks CI will run:

```bash
pip install ruff mypy pytest
ruff check .
mypy .
pytest
```

## Submitting a pull request

- Describe what the change does and why
- Reference any related issue (e.g. `Fixes #12`)
- Be ready to discuss and iterate — reviews are meant to improve the change, not gatekeep it

## Reporting bugs / requesting features

Please open a GitHub issue using the appropriate template. For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead — do not open a public issue.

## Code of conduct

Be respectful and constructive. This is a small open-source project maintained in spare time — patience and clear communication go a long way.
