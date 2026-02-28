#!/usr/bin/env python3
"""Entry point for boni — your grumpy AI desktop companion."""

import sys


def main():
    print("🐾 Starting boni...")
    print("   boni lives in your menu bar now.")
    print("   Press Ctrl+C to quit.\n")

    try:
        from boni.app import BoniApp

        app = BoniApp()
        app.run()
    except KeyboardInterrupt:
        print("\n👋 boni has left the building.")
        sys.exit(0)
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
