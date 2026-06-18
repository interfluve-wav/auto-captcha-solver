#!/usr/bin/env python3
"""
auto-captcha CLI — solve captchas from the command line.

Usage:
    auto-captcha solve --url https://example.com --key YOUR_KEY
    auto-captcha credits --key YOUR_KEY
    auto-captcha detect --url https://example.com --key YOUR_KEY
    auto-captcha solve --provider captchaai --key YOUR_CAPTCHAAI_KEY --url ...
"""

import argparse
import json
import os
import sys
import time


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=["nopecha", "captchaai"],
        default=os.environ.get("CAPTCHA_PROVIDER", "nopecha"),
        help="Solve provider (default: nopecha, or CAPTCHA_PROVIDER env)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="API key (or set NOPECHA_API_KEY / CAPTCHAAI_API_KEY)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="auto-captcha",
        description="Universal captcha solver for Playwright automation",
    )
    sub = parser.add_subparsers(dest="command")

    solve_p = sub.add_parser("solve", help="Solve captchas on a URL")
    solve_p.add_argument("--url", required=True, help="Page URL with captcha")
    _add_provider_args(solve_p)
    solve_p.add_argument("--headless", action="store_true", default=True)
    solve_p.add_argument("--no-headless", action="store_false", dest="headless")
    solve_p.add_argument("--timeout", type=float, default=120, help="Solve timeout in seconds")

    detect_p = sub.add_parser("detect", help="Detect captchas without solving")
    detect_p.add_argument("--url", required=True, help="Page URL")
    _add_provider_args(detect_p)
    detect_p.add_argument("--headless", action="store_true", default=True)

    credits_p = sub.add_parser("credits", help="Check provider credit balance")
    _add_provider_args(credits_p)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    from auto_captcha_solver import CaptchaSolver
    from auto_captcha_solver.providers import resolve_api_key
    from auto_captcha_solver.types import sanitize_detect_results

    api_key = resolve_api_key(args.provider, args.key)
    if not api_key:
        print(
            f"Error: API key required for provider '{args.provider}'. "
            "Set NOPECHA_API_KEY or CAPTCHAAI_API_KEY, or pass --key",
            file=sys.stderr,
        )
        sys.exit(1)

    solver = CaptchaSolver(api_key=api_key, provider=args.provider)

    if args.command == "credits":
        credits = solver.get_credits()
        print(json.dumps({"provider": args.provider, "credits": credits}))

    elif args.command == "detect":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            captchas = sanitize_detect_results(solver.detect(page))
            browser.close()
        print(json.dumps(captchas, indent=2, default=str))

    elif args.command == "solve":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            if hasattr(args, "timeout"):
                solver.timeout_sec = args.timeout
            results = solver.auto_solve(page)
            browser.close()

        output = []
        for r in results:
            output.append(
                {
                    "provider": args.provider,
                    "type": r.captcha_type,
                    "success": r.success,
                    "token": r.token[:50] + "..." if len(r.token) > 50 else r.token,
                    "error": r.error,
                    "attempts": r.attempts,
                    "elapsed_sec": r.elapsed_sec,
                }
            )
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
