"""Inzar Management CLI."""

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, validate_password_strength
from app.db.session import AsyncSessionLocal
from app.modules.users.service import UserService


async def create_admin(
    email: str,
    password: str,
    display_name: str | None,
    session: AsyncSession | None = None,
) -> None:
    validate_password_strength(password)
    hashed_password = hash_password(password)

    if session is not None:
        user_service = UserService(session)
        existing = await user_service.get_by_email(email)
        if existing:
            raise ValueError(f"User with email '{email}' already exists.")
        user = await user_service.create_user(
            email=email,
            password_hash=hashed_password,
            display_name=display_name or "Administrator",
            role="admin",
            email_verified_at=datetime.now(UTC),
        )
        print(f"Admin user successfully created with ID: {user.id}")
        return

    async with AsyncSessionLocal() as session_ctx:
        user_service = UserService(session_ctx)
        existing = await user_service.get_by_email(email)
        if existing:
            print(f"Error: User with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        user = await user_service.create_user(
            email=email,
            password_hash=hashed_password,
            display_name=display_name or "Administrator",
            role="admin",
            email_verified_at=datetime.now(UTC),
        )
        await session_ctx.commit()
        print(f"Admin user successfully created with ID: {user.id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inzar Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: create-admin
    admin_parser = subparsers.add_parser("create-admin", help="Create an initial admin user")
    admin_parser.add_argument("--email", required=True, help="Admin email address")
    admin_parser.add_argument("--password", required=True, help="Admin password")
    admin_parser.add_argument("--display-name", default="Administrator", help="Admin display name")

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(create_admin(args.email, args.password, args.display_name))


if __name__ == "__main__":
    main()
