#!/usr/bin/env python3
"""
auto-captcha CLI — solve captchas from the command line.

Usage:
    auto-captcha solve --url https://example.com --key YOUR_KEY
    auto-captcha credits --key YOUR_KEY
    auto-captcha detect --url https://example.com --key YOUR_KEY
"""

import argparse
import json
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(
        prog="auto-captcha",
        description="Universal captcha solver for Playwright automation",
    )
    sub = parser.add_subparsers(dest="command")

    # -- solve --
    solve_p = sub.add_parser("solve", help="Solve captchas on a URL")
    solve_p.add_argument("--url", required=True, help="Page URL with captcha")
    solve_p.add_argument("--key", default=os.environ.get("NOPECHA_API_KEY", ""), help="NopeCHA API key")
    solve_p.add_argument("--headless", action="store_true", default=True)
    solve_p.add_argument("--no-headless", action="store_false", dest="headless")
    solve_p.add_argument("--timeout", type=float, default=120, help="Solve timeout in seconds")

    # -- detect --
    detect_p = sub.add_parser("detect", help="Detect captchas without solving")
    detect_p.add_argument("--url", required=True, help="Page URL")
    detect_p.add_argument("--key", default=os.environ.get("NOPECHA_API_KEY", ""), help="NopeCHA API key")
    detect_p.add_argument("--headless", action="store_true", default=True)

    # -- credits --
    credits_p = sub.add_parser("credits", help="Check NopeCHA credit balance")
    credits_p.add_argument("--key", default=os.environ.get("NOPECHA_API_KEY", ""), help="NopeCHA API key")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not args.key:
        print("Error: NopeCHA API key required. Set NOPECHA_API_KEY or use --key", file=sys.stderr)
        sys.exit(1)

    from auto_captcha import CaptchaSolver

    solver = CaptchaSolver(api_key=args.key)

    if args.command == "credits":
        credits = solver.get_credits()
        print(json.dumps({"credits": credits}))

    elif args.command == "detect":
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            captchas = solver.detect(page)
            browser.close()
        print(json.dumps(captchas, indent=2, default=str))

    elif args.command == "solve":
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            results = solver.auto_solve(page)
            browser.close()

        output = []
        for r in results:
            output.append({
                "type": r.captcha_type,
                "success": r.success,
                "token": r.token[:50] + "..." if len(r.token) > 50 else r.token,
                "error": r.error,
                "attempts": r.attempts,
                "elapsed_sec": r.elapsed_sec,
            })
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
