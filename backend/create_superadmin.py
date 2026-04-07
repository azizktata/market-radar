import os
from dotenv import load_dotenv

load_dotenv()

from auth import get_conn, hash_password

SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL")
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD")
SUPERADMIN_NAME = os.environ.get("SUPERADMIN_NAME", "Super Admin")


def create_superadmin():
    if not SUPERADMIN_EMAIL or not SUPERADMIN_PASSWORD:
        print("SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD must be set")
        return False

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (SUPERADMIN_EMAIL,))
        existing = cur.fetchone()

        if existing:
            cur.execute(
                "UPDATE users SET name = ?, role = 'superadmin', is_active = 1 WHERE email = ?",
                (SUPERADMIN_NAME, SUPERADMIN_EMAIL),
            )
            user_id = existing["id"]
        else:
            password_hash = hash_password(SUPERADMIN_PASSWORD)
            cur.execute(
                "INSERT INTO users (email, name, password_hash, role, is_active) VALUES (?, ?, ?, 'superadmin', 1)",
                (SUPERADMIN_EMAIL, SUPERADMIN_NAME, password_hash),
            )
            user_id = cur.lastrowid

        conn.commit()

        cur.execute("SELECT id FROM companies WHERE name = ?", (SUPERADMIN_NAME,))
        company = cur.fetchone()
        if company:
            company_id = company["id"]
        else:
            cur.execute("INSERT INTO companies (name) VALUES (?)", (SUPERADMIN_NAME,))
            company_id = cur.lastrowid

        conn.commit()

        cur.execute("SELECT 1 FROM user_companies WHERE user_id = ? AND company_id = ?", (user_id, company_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO user_companies (user_id, company_id) VALUES (?, ?)", (user_id, company_id))
            conn.commit()

        print("Superadmin ready")
        return True
    except Exception as e:
        print(f"Error creating superadmin: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    create_superadmin()
