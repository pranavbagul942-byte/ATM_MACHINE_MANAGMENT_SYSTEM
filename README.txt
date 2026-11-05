# SBI ATM Multi-user GUI + SQLite
#created by Pranav Bagul

## Features
- Four demo users in one SQLite database
- Login using account number and PIN
- Deposit, withdrawal, balance inquiry and PIN change
- Fund transfer between demo accounts
- Mini statement (last 10 transactions)
- PIN verification before deposit, withdrawal and transfer
- Daily withdrawal limit of ₹20,000 per account
- Transaction receipts and persistent database storage
- PINs stored as salted PBKDF2-HMAC-SHA256 hashes

## Run
1. Keep `atm_gui.py` in a folder.
2. Open Command Prompt in that folder.
3. Run `python atm_gui.py`.

No third-party packages are required. Tkinter and SQLite are included with most standard Windows Python installations.

## Demo users
- Account `1001`: Pranav Bagul; initial PIN `1234` only if creating a new database.
- Account `1002`: Sanika Kharate.
- Account `1003`: Janhavi Marathi.
- Account `1004`: Arpita Pokle.

For newly created accounts, random 4-digit initial PINs are saved to `demo_accounts.txt` in the same folder. Open that file to see the initial PINs. Existing accounts and PINs are not reset if the database already exists.

## Existing database
Keep your existing `atm_database.db` in the same folder as `atm_gui.py` to preserve your balance and PIN for account 1001. Back up the database before replacing project files.

## Important
This is a college/demo simulator, not real banking software. It does not connect to SBI or any banking network. The random demo PINs are stored in a local credentials text file for convenience; keep that file private and delete it after recording the PINs safely if desired.
