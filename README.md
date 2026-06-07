# Mail Merge — Local Flask App

Send personalised Gmail emails from an Excel list. Runs entirely on your machine.

## Setup (one time)

**Requirements:** Python 3.8+

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py
```

Then open your browser at → **http://localhost:5000**

## How to use

1. **Step 1 — Gmail setup**
   - Enter your Gmail address
   - Enter your App Password (not your regular password)
     - Get one at: myaccount.google.com/security → App Passwords
   - Enter your display name

2. **Step 2 — Load Excel**
   - Upload your `.xlsx`, `.xls`, or `.csv` file
   - Map your columns to Name / Email / Lead Name / Lead Email
   - Any extra columns automatically become available as `{{ColumnName}}` variables

3. **Step 3 — Compose & Send**
   - Write your subject and body using `{{Name}}`, `{{Lead Name}}`, etc.
   - Preview shows how the first email will look
   - Use "Test" to send just to yourself first
   - "Send all" sends one personal email per row, CC-ing the lead

## Notes

- Emails are sent individually (not BCC) so each recipient sees only their own email
- Lead email is added as CC on each individual send
- A delay between sends avoids Gmail spam filters (4 seconds recommended)
- Nothing is sent to any external server — your credentials stay on your machine
