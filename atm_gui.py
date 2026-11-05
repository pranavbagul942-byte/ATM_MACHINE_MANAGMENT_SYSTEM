"""
SBI ATM Management System — Multi-user GUI + SQLite
Educational simulator only; not for real banking use.

Run: python atm_gui.py
Demo account (fresh database): 1001 / 1234
Newly created users' random PINs are written once to demo_accounts.txt.
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from datetime import date

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "atm_database.db"
CREDENTIALS_PATH = APP_DIR / "demo_accounts.txt"

NAVY = "#10233F"
BLUE = "#1D4ED8"
LIGHT_BG = "#F3F6FB"
WHITE = "#FFFFFF"
TEXT = "#172033"
MUTED = "#64748B"
GREEN = "#15803D"
RED = "#B91C1C"

DAILY_WITHDRAWAL_LIMIT = 20000


def hash_pin(pin: str, salt: bytes | None = None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return salt, digest


def random_pin():
    return f"{secrets.randbelow(9000) + 1000:04d}"


class ATMDatabase:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()
        self.seed_accounts()

    def create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_no TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mobile TEXT NOT NULL DEFAULT '',
                    account_type TEXT NOT NULL DEFAULT 'Savings',
                    bank_name TEXT NOT NULL DEFAULT 'SBI',
                    pin_salt BLOB NOT NULL,
                    pin_hash BLOB NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 10000 CHECK(balance >= 0)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_no TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    balance_after INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(account_no) REFERENCES accounts(account_no)
                )
            """)

        # Migrate an older version of this project which did not have a note column.
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(transactions)")}
        if "note" not in columns:
            with self.conn:
                self.conn.execute("ALTER TABLE transactions ADD COLUMN note TEXT NOT NULL DEFAULT ''")

    def seed_accounts(self):
        # Keep the original demo account and its existing PIN/balance unchanged.
        original = self.conn.execute(
            "SELECT account_no FROM accounts WHERE account_no = ?", ("1001",)
        ).fetchone()
        if not original:
            salt, digest = hash_pin("1234")
            with self.conn:
                self.conn.execute("""
                    INSERT INTO accounts
                    (account_no, name, mobile, account_type, bank_name, pin_salt, pin_hash, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, ("1001", "Pranav Bagul", "", "Savings", "SBI", salt, digest, 10000))

        # New demo users receive random 4-digit PINs only when first created.
        new_users = [
            ("1002", "Sanika Kharate"),
            ("1003", "Janhavi Marathi"),
            ("1004", "Arpita Pokle"),
        ]
        credentials_created = []
        for account_no, name in new_users:
            exists = self.conn.execute(
                "SELECT account_no FROM accounts WHERE account_no = ?", (account_no,)
            ).fetchone()
            if exists:
                continue
            pin = random_pin()
            salt, digest = hash_pin(pin)
            with self.conn:
                self.conn.execute("""
                    INSERT INTO accounts
                    (account_no, name, mobile, account_type, bank_name, pin_salt, pin_hash, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (account_no, name, "", "Savings", "SBI", salt, digest, 10000))
            credentials_created.append((account_no, name, pin))

        if credentials_created:
            new_file = not CREDENTIALS_PATH.exists()
            with CREDENTIALS_PATH.open("a", encoding="utf-8") as f:
                if new_file:
                    f.write("ATM DEMO ACCOUNT CREDENTIALS\n")
                    f.write("Keep this file private. These are demo credentials only.\n\n")
                for account_no, name, pin in credentials_created:
                    f.write(f"Account: {account_no} | Name: {name} | Initial PIN: {pin}\n")
            print("New demo accounts created. Initial PINs saved in demo_accounts.txt.")

    def authenticate(self, account_no, pin):
        account = self.conn.execute(
            "SELECT * FROM accounts WHERE account_no = ?", (account_no.strip(),)
        ).fetchone()
        if not account:
            return None
        _, digest = hash_pin(pin, account["pin_salt"])
        return dict(account) if hmac.compare_digest(digest, account["pin_hash"]) else None

    def get_account(self, account_no):
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE account_no = ?", (account_no,)
        ).fetchone()
        return dict(row) if row else None

    def update_pin(self, account_no, new_pin):
        salt, digest = hash_pin(new_pin)
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET pin_salt = ?, pin_hash = ? WHERE account_no = ?",
                (salt, digest, account_no)
            )

    def change_balance(self, account_no, amount, transaction_type):
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        with self.conn:
            row = self.conn.execute(
                "SELECT balance FROM accounts WHERE account_no = ?", (account_no,)
            ).fetchone()
            if row is None:
                raise ValueError("Account not found.")
            current = int(row["balance"])

            if transaction_type == "Withdrawal":
                if amount > current:
                    raise ValueError("Insufficient balance.")
                today = date.today().isoformat()
                used_row = self.conn.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM transactions
                    WHERE account_no = ? AND transaction_type = 'Withdrawal'
                      AND date(created_at) = ?
                """, (account_no, today)).fetchone()
                used = int(used_row["total"])
                if used + amount > DAILY_WITHDRAWAL_LIMIT:
                    remaining = max(0, DAILY_WITHDRAWAL_LIMIT - used)
                    raise ValueError(
                        f"Daily withdrawal limit is ₹{DAILY_WITHDRAWAL_LIMIT:,}.\n"
                        f"Your remaining limit today is ₹{remaining:,}."
                    )
                new_balance = current - amount
            else:
                new_balance = current + amount

            self.conn.execute(
                "UPDATE accounts SET balance = ? WHERE account_no = ?",
                (new_balance, account_no)
            )
            self.conn.execute("""
                INSERT INTO transactions
                (account_no, transaction_type, amount, balance_after, note)
                VALUES (?, ?, ?, ?, '')
            """, (account_no, transaction_type, amount, new_balance))
        return new_balance

    def transfer(self, sender, receiver, amount):
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        if sender == receiver:
            raise ValueError("You cannot transfer money to the same account.")
        with self.conn:
            source = self.conn.execute(
                "SELECT balance FROM accounts WHERE account_no = ?", (sender,)
            ).fetchone()
            target = self.conn.execute(
                "SELECT account_no, balance, name FROM accounts WHERE account_no = ?", (receiver,)
            ).fetchone()
            if source is None or target is None:
                raise ValueError("Recipient account not found.")
            source_balance = int(source["balance"])
            if amount > source_balance:
                raise ValueError("Insufficient balance.")
            new_source = source_balance - amount
            new_target = int(target["balance"]) + amount
            self.conn.execute("UPDATE accounts SET balance = ? WHERE account_no = ?", (new_source, sender))
            self.conn.execute("UPDATE accounts SET balance = ? WHERE account_no = ?", (new_target, receiver))
            self.conn.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, balance_after, note)
                VALUES (?, 'Transfer Out', ?, ?, ?)
            """, (sender, amount, new_source, f"To {receiver}"))
            self.conn.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, balance_after, note)
                VALUES (?, 'Transfer In', ?, ?, ?)
            """, (receiver, amount, new_target, f"From {sender}"))
        return new_source, target["name"]

    def transactions_for(self, account_no, limit=100):
        return self.conn.execute("""
            SELECT transaction_type, amount, balance_after, note, created_at
            FROM transactions WHERE account_no = ?
            ORDER BY id DESC LIMIT ?
        """, (account_no, limit)).fetchall()

    def close(self):
        self.conn.close()


class ATMApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SBI ATM Management System")
        self.geometry("1020x690")
        self.minsize(880, 600)
        self.configure(bg=LIGHT_BG)
        self.db = ATMDatabase()
        self.account_no = None
        self.account = None

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def header(self, title, subtitle):
        banner = tk.Frame(self, bg=NAVY, height=118)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text=title, bg=NAVY, fg=WHITE,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=30, pady=(23, 2))
        tk.Label(banner, text=subtitle, bg=NAVY, fg="#DCE7F7",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=32)

    def show_login(self):
        self.account_no = None
        self.account = None
        self.clear()
        self.header("SBI ATM", "ATM Management System  •  Multi-user Demo")
        content = tk.Frame(self, bg=LIGHT_BG)
        content.pack(expand=True, fill="both", padx=25, pady=25)
        card = tk.Frame(content, bg=WHITE, highlightbackground="#DCE4F0", highlightthickness=1)
        card.place(relx=0.5, rely=0.47, anchor="center", width=470, height=385)

        tk.Label(card, text="Welcome back", bg=WHITE, fg=NAVY,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=30, pady=(24, 4))
        tk.Label(card, text="Sign in with your account number and PIN",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=30, pady=(0, 18))
        tk.Label(card, text="Account number", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=30)
        self.account_entry = ttk.Entry(card, font=("Segoe UI", 12))
        self.account_entry.pack(fill="x", padx=30, pady=(5, 12), ipady=5)
        self.account_entry.insert(0, "1001")
        tk.Label(card, text="4-digit PIN", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=30)
        self.pin_entry = ttk.Entry(card, show="•", font=("Segoe UI", 12))
        self.pin_entry.pack(fill="x", padx=30, pady=(5, 17), ipady=5)
        self.pin_entry.bind("<Return>", lambda _event: self.login())
        tk.Button(card, text="LOGIN", command=self.login, bg=BLUE, fg=WHITE,
                  activebackground="#1E40AF", activeforeground=WHITE, relief="flat",
                  font=("Segoe UI", 11, "bold"), cursor="hand2").pack(
                      fill="x", padx=30, ipady=8)
        tk.Label(content, text="Demo accounts start with ₹10,000 each. New random PINs are in demo_accounts.txt.",
                 bg=LIGHT_BG, fg=MUTED, font=("Segoe UI", 9), wraplength=650).pack(side="bottom", pady=(0, 2))
        self.account_entry.focus_set()

    def login(self):
        account_no = self.account_entry.get().strip()
        pin = self.pin_entry.get().strip()
        if not account_no or not pin:
            messagebox.showwarning("Missing details", "Enter account number and PIN.")
            return
        account = self.db.authenticate(account_no, pin)
        if account is None:
            messagebox.showerror("Login failed", "Incorrect account number or PIN.")
            self.pin_entry.delete(0, tk.END)
            self.pin_entry.focus_set()
            return
        self.account_no = account_no
        self.account = account
        self.show_dashboard()

    def refresh_account(self):
        self.account = self.db.get_account(self.account_no)

    def show_dashboard(self):
        self.refresh_account()
        self.clear()
        self.header("SBI ATM Dashboard", f"Welcome, {self.account['name']}  •  Account ending {self.account_no[-4:]}")
        body = tk.Frame(self, bg=LIGHT_BG)
        body.pack(fill="both", expand=True, padx=28, pady=22)

        top = tk.Frame(body, bg=WHITE, highlightbackground="#DCE4F0", highlightthickness=1)
        top.pack(fill="x", pady=(0, 12))
        tk.Label(top, text="AVAILABLE BALANCE", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=24, pady=(15, 2))
        self.balance_label = tk.Label(top, text=f"₹ {self.account['balance']:,}",
                                      bg=WHITE, fg=NAVY, font=("Segoe UI", 25, "bold"))
        self.balance_label.pack(anchor="w", padx=24, pady=(0, 14))

        grid = tk.Frame(body, bg=LIGHT_BG)
        grid.pack(fill="both", expand=True)
        actions = [
            ("＋  Deposit Money", self.deposit),
            ("－  Withdraw Money", self.withdraw),
            ("⇄  Transfer Funds", self.transfer),
            ("◉  Check Balance", self.check_balance),
            ("↻  Change PIN", self.change_pin),
            ("▤  Mini Statement", self.show_history),
            ("♙  User Information", self.show_user_info),
            ("↪  Log Out", self.logout),
        ]
        for index, (label, command) in enumerate(actions):
            r, c = divmod(index, 4)
            tk.Button(grid, text=label, command=command, bg=WHITE, fg=NAVY,
                      activebackground="#E8F0FF", activeforeground=NAVY,
                      relief="flat", bd=0, highlightbackground="#DCE4F0",
                      highlightthickness=1, font=("Segoe UI", 10, "bold"),
                      cursor="hand2", wraplength=180).grid(
                          row=r, column=c, sticky="nsew", padx=5, pady=5, ipady=17)
            grid.grid_columnconfigure(c, weight=1, uniform="col")
            grid.grid_rowconfigure(r, weight=1, uniform="row")

        tk.Label(body, text=f"Daily cash withdrawal limit: ₹{DAILY_WITHDRAWAL_LIMIT:,}",
                 bg=LIGHT_BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

    def verify_pin(self, purpose):
        pin = simpledialog.askstring("Verify PIN", f"Enter your PIN to {purpose}:", show="•", parent=self)
        if pin is None:
            return False
        if self.db.authenticate(self.account_no, pin) is None:
            messagebox.showerror("Verification failed", f"Incorrect PIN. {purpose.capitalize()} cancelled.")
            return False
        return True

    def ask_amount(self, title, prompt):
        value = simpledialog.askstring(title, prompt, parent=self)
        if value is None:
            return None
        try:
            amount = int(value.strip())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a whole-number amount.")
            return None
        if amount <= 0:
            messagebox.showerror("Invalid amount", "Amount must be greater than zero.")
            return None
        return amount

    def show_receipt(self, title, transaction, amount, balance, note=""):
        details = f"{transaction} successful\nAmount: ₹{amount:,}\nAvailable balance: ₹{balance:,}"
        if note:
            details += f"\n{note}"
        details += "\n\nEducational ATM receipt"
        messagebox.showinfo(title, details)

    def update_balance_label(self):
        self.refresh_account()
        self.balance_label.config(text=f"₹ {self.account['balance']:,}")

    def deposit(self):
        if not self.verify_pin("deposit money"):
            return
        amount = self.ask_amount("Deposit Money", "Enter amount to deposit (₹):")
        if amount is None:
            return
        try:
            balance = self.db.change_balance(self.account_no, amount, "Deposit")
            self.update_balance_label()
            self.show_receipt("Deposit Receipt", "Deposit", amount, balance)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Deposit failed", str(exc))

    def withdraw(self):
        if not self.verify_pin("withdraw money"):
            return
        amount = self.ask_amount("Withdraw Money", "Enter amount to withdraw (₹):")
        if amount is None:
            return
        try:
            balance = self.db.change_balance(self.account_no, amount, "Withdrawal")
            self.update_balance_label()
            self.show_receipt("Withdrawal Receipt", "Withdrawal", amount, balance)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Withdrawal failed", str(exc))

    def transfer(self):
        if not self.verify_pin("transfer funds"):
            return
        receiver = simpledialog.askstring("Transfer Funds", "Enter recipient account number:", parent=self)
        if receiver is None:
            return
        receiver = receiver.strip()
        target = self.db.get_account(receiver)
        if not target:
            messagebox.showerror("Transfer failed", "Recipient account was not found.")
            return
        if receiver == self.account_no:
            messagebox.showerror("Transfer failed", "You cannot transfer to your own account.")
            return
        if not messagebox.askyesno("Confirm Transfer", f"Transfer to {target['name']} (account ending {receiver[-4:]})?"):
            return
        amount = self.ask_amount("Transfer Funds", "Enter amount to transfer (₹):")
        if amount is None:
            return
        try:
            balance, recipient_name = self.db.transfer(self.account_no, receiver, amount)
            self.update_balance_label()
            self.show_receipt("Transfer Receipt", f"Transfer to {recipient_name}", amount, balance)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Transfer failed", str(exc))

    def check_balance(self):
        self.update_balance_label()
        messagebox.showinfo("Current Balance", f"Your current balance is ₹ {self.account['balance']:,}.")

    def change_pin(self):
        old_pin = simpledialog.askstring("Change PIN", "Enter current PIN:", show="•", parent=self)
        if old_pin is None:
            return
        if self.db.authenticate(self.account_no, old_pin) is None:
            messagebox.showerror("PIN change failed", "Current PIN is incorrect.")
            return
        new_pin = simpledialog.askstring("Change PIN", "Enter new 4-digit PIN:", show="•", parent=self)
        if new_pin is None:
            return
        if len(new_pin) != 4 or not new_pin.isdigit():
            messagebox.showerror("Invalid PIN", "PIN must contain exactly 4 digits.")
            return
        if new_pin == old_pin:
            messagebox.showwarning("Choose another PIN", "New PIN must be different from current PIN.")
            return
        self.db.update_pin(self.account_no, new_pin)
        messagebox.showinfo("Success", "Your PIN has been changed successfully.")

    def show_user_info(self):
        self.refresh_account()
        mobile = self.account["mobile"] or "Not configured"
        if mobile.isdigit() and len(mobile) >= 4:
            mobile = "******" + mobile[-4:]
        messagebox.showinfo(
            "User Information",
            f"Name: {self.account['name']}\n"
            f"Account Number: {self.account['account_no']}\n"
            f"Mobile Number: {mobile}\n"
            f"Account Type: {self.account['account_type']}\n"
            f"Bank Name: {self.account['bank_name']}"
        )

    def show_history(self):
        rows = self.db.transactions_for(self.account_no, 10)
        window = tk.Toplevel(self)
        window.title("Mini Statement")
        window.geometry("820x430")
        window.configure(bg=LIGHT_BG)
        tk.Label(window, text="Mini Statement — Last 10 Transactions", bg=LIGHT_BG, fg=NAVY,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        columns = ("date", "type", "amount", "balance", "note")
        tree = ttk.Treeview(window, columns=columns, show="headings")
        for col, label, width in [
            ("date", "Date / Time", 180), ("type", "Transaction", 130),
            ("amount", "Amount (₹)", 110), ("balance", "Balance (₹)", 120),
            ("note", "Details", 160)
        ]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w" if col in ("date", "type", "note") else "e")
        tree.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        for row in rows:
            tree.insert("", "end", values=(
                row["created_at"], row["transaction_type"],
                f"{row['amount']:,}", f"{row['balance_after']:,}", row["note"]
            ))
        if not rows:
            tk.Label(window, text="No transactions yet.", bg=LIGHT_BG, fg=MUTED).pack(pady=(0, 15))

    def logout(self):
        if messagebox.askyesno("Log Out", "Do you want to log out?"):
            self.show_login()

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = ATMApp()
    app.mainloop()
