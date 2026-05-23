#!/usr/bin/env python3
"""
Login script using instagrapi (Session ID & Mobile API emulation).
"""
import os, sys, json, logging

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ChallengeUnknownStep,
    TwoFactorRequired,
)

IG_USER = os.getenv("INSTAGRAM_USERNAME")
IG_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID")  

SESSION_DIR = os.path.expanduser("~/.config/instagrapi")
SESSION_FILE = os.path.join(SESSION_DIR, f"session-{IG_USER}.json")


def challenge_code_handler(username, choice):
    print(f"\n{'='*50}")
    print(f"Instagram requires verification for @{username}")
    print(f"Verification method: {choice}")
    print(f"{'='*50}")
    return input("Enter the verification code sent to you: ").strip()


def change_password_handler(username):
    print(f"\nInstagram requires a password change for @{username}")
    return input("Enter new password: ").strip()


def main():
    if not IG_USER or not IG_SESSION_ID:
        print("ERROR: Set INSTAGRAM_USERNAME and INSTAGRAM_SESSION_ID in .env")
        sys.exit(1)

    os.makedirs(SESSION_DIR, exist_ok=True)

    cl = Client()
    
    # Configure device settings
    cl.set_device({
        "app_version": "316.0.0.38.109",
        "android_version": 33,
        "android_release": "13",
        "dpi": "420dpi",
        "resolution": "1080x2340",
        "manufacturer": "Google",
        "device": "cheetah",
        "model": "Pixel 7 Pro",
        "cpu": "tensor",
        "version_code": "563503248"
    })
    
    cl.challenge_code_handler = challenge_code_handler
    cl.change_password_handler = change_password_handler
    cl.delay_range = [1, 3]

    # --- Check for Existing Saved Session First ---
    if os.path.exists(SESSION_FILE):
        print(f"Attempting to load saved session from: {SESSION_FILE}")
        try:
            cl.load_settings(SESSION_FILE)
            cl.get_timeline_feed()  # Quick test request to verify the file works
            print("✅ Valid saved session loaded successfully!")
            print(f"Now restart the bot: python main.py")
            sys.exit(0)
        except Exception as e:
            print(f"Saved session expired or invalid: {e}. Authenticating with Session ID...")

    # --- Fallback to Session ID Authentication ---
    print(f"Logging in as @{IG_USER} via Session ID...")
    try:
        cl.login_by_sessionid(IG_SESSION_ID)
    except ChallengeUnknownStep as e:
        print(f"\nInstagram triggered an unresolvable challenge.")
        print(f"Details: {e}")
        sys.exit(1)
    except ChallengeRequired as e:
        print(f"\nChallenge required: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    # Save settings to file for future executions
    cl.dump_settings(SESSION_FILE)
    print(f"\n✅ Login successful! New session saved to: {SESSION_FILE}")

    try:
        user_info = cl.user_info_by_username(IG_USER)
        print(f"Verified: @{user_info.username} (ID: {user_info.pk})")
    except Exception as e:
        print(f"Warning: Session saved but validation failed: {e}")

    print(f"\nNow restart the bot: python main.py")


if __name__ == "__main__":
    main()
