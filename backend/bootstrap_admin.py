"""
SmartGuard AI — Administrator Bootstrap Script

Usage:
    python bootstrap_admin.py

Reads username and password from interactive prompts (never from command-line args).
Creates the first ADMIN account only if no administrator exists.

PowerShell command:
    cd D:\Gate-Security-System\backend
    .\venv\Scripts\python.exe bootstrap_admin.py
"""
import getpass
import sys
import os
from pathlib import Path

# Make the backend package importable
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import db_session, check_db_connectivity
from app.services.account_service import AccountService


def main() -> None:
    print("=" * 60)
    print("  SmartGuard AI — Administrator Bootstrap")
    print("=" * 60)
    print()

    # Verify database is reachable before prompting for credentials
    print("Checking database connectivity...")
    if not check_db_connectivity():
        print("\nERROR: Cannot reach the database.")
        print("  Verify DATABASE_URL in backend/.env and that your Supabase project is accessible.")
        sys.exit(1)
    print("Database connected.\n")

    # Collect account details
    username = input("Admin username (e.g. admin): ").strip()
    if not username:
        print("ERROR: Username cannot be empty.")
        sys.exit(1)
    if len(username) < 3:
        print("ERROR: Username must be at least 3 characters.")
        sys.exit(1)

    full_name = input("Full name: ").strip()
    if not full_name:
        print("ERROR: Full name cannot be empty.")
        sys.exit(1)

    # Use getpass so the password is never echoed to the terminal
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("ERROR: Passwords do not match.")
        sys.exit(1)

    print("\nCreating administrator account...")
    try:
        with db_session() as db:
            service = AccountService(db)
            account = service.bootstrap_admin(username, password, full_name)
        print(f"\nSuccess! Administrator account created.")
        print(f"  ID:       {account.id}")
        print(f"  Username: {account.username}")
        print(f"  Name:     {account.full_name}")
        print(f"  Role:     {account.role}")
        print()
        print("You can now log in at http://localhost:5173")
    except ValueError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
