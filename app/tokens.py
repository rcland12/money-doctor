"""Manage API tokens from the command line (e.g. for a server that calls the app).

  python -m app.tokens create my-server        # prints the token once
  python -m app.tokens list
"""

import sys

from sqlalchemy import select

from .auth import new_token
from .models import ApiToken, Session, init_db


def main() -> None:
    init_db()
    if len(sys.argv) >= 3 and sys.argv[1] == "create":
        print(new_token(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "list":
        with Session() as s:
            for t in s.scalars(select(ApiToken)):
                print(t.id, t.name, t.created_at, t.last_used or "never used")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
