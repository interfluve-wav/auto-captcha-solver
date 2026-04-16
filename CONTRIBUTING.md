# Contributing

Contributions welcome!

## Setup

```bash
git clone https://github.com/interfluve-wav/auto-captcha.git
cd auto-captcha
pip install -e ".[all]"
```

## Testing

```bash
export NOPECHA_API_KEY="your-key"
python -m auto_captcha.solver      # Run solver test
python -m auto_captcha.auto_captcha # Run full flow test
```

## Submitting Changes

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push to your fork
5. Open a Pull Request

## Code Style

- Python 3.9+
- Type hints encouraged
- Docstrings for public methods
