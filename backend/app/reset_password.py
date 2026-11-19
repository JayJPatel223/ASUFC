"""Operator-only password recovery. Requires trusted database access."""
import getpass
import os
from .main import db,audit
from .credentials import hash_password,validate_password

def reset_password(password):
    validate_password(password)
    user=os.environ.get("STAFF_USER","staff")
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(2663002)")
        row=c.execute("UPDATE staff_credential SET password_hash=%s,updated_at=now() WHERE username=%s RETURNING username",(hash_password(password),user)).fetchone()
        if not row: raise SystemExit("Initialize the application first")
        c.execute("DELETE FROM staff_session")
        c.execute("DELETE FROM staff_login_attempt")
        audit(c,"password_reset","staff_account",0,{"method":"operator"})

def main():
    password=getpass.getpass("New staff password: ")
    if password!=getpass.getpass("Repeat password: "): raise SystemExit("Passwords differ")
    reset_password(password)
    print("Password reset. All staff sessions revoked.")
if __name__=="__main__": main()
