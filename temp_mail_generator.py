import requests
import re
import time
import random
import string
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

class TempMailGenerator:
    """
    Advanced Temporary Mail Generator with OTP/Code Extraction
    Features: Multiple providers, auto-code detection, real-time checking
    """
    
    def __init__(self):
        self.base_url = "https://www.1secmail.com/api/v1/"
        self.email = None
        self.login = None
        self.domain = None
        self.last_http_status = None
        self.last_http_error = None
        self._last_inbox: List[Dict] = []
        self._last_inbox_ts: float = 0.0
        self._min_fetch_interval_sec: float = 6.0
        # Provider handling
        self.provider = "1secmail"  # or "mailtm"
        self.mailtm_token = None
        self.mailtm_address = None
        self.mailtm_account_id = None
        
    def _get_json(self, url: str) -> Optional[Dict]:
        """Fetch URL and return parsed JSON or None on failure."""
        self.last_http_status = None
        self.last_http_error = None
        # Rotate a couple of common User-Agents to reduce 403s
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/126.0",
        ]
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": random.choice(user_agents),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        # Simple retry with backoff to handle transient 403/5xx
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                self.last_http_status = resp.status_code
                if resp.status_code == 403:
                    # Provider may block rapid polling; backoff and retry
                    time.sleep(1.5 * (attempt + 1))
                    resp.raise_for_status()
                resp.raise_for_status()
                try:
                    return resp.json()
                except Exception:
                    preview = (resp.text or "").strip()[:120]
                    print(f"❌ Non-JSON response from provider: {preview}")
                    return None
            except requests.HTTPError as e:
                self.last_http_error = str(e)
                if getattr(e, "response", None) is not None:
                    self.last_http_status = e.response.status_code
                # Backoff and retry on 403/429/5xx
                if self.last_http_status in (403, 429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                print(f"❌ HTTP error: {e}")
                return None
            except Exception as e:
                self.last_http_error = str(e)
                print(f"❌ HTTP error: {e}")
                return None

    def _sanitize_filename(self, name: str) -> str:
        safe = re.sub(r"[\\/:*?\"<>|]", "_", name)
        safe = re.sub(r"\s+", " ", safe).strip()
        return safe or "email"

    def _ensure_output_dir(self, output_dir: str) -> str:
        if not output_dir:
            output_dir = "inbox"
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def get_available_domains(self) -> List[str]:
        """Get list of available domains"""
        if self.provider == "1secmail":
            data = self._get_json(f"{self.base_url}?action=getDomainList")
            if isinstance(data, list):
                return data
            return []
        # mail.tm
        try:
            resp = requests.get("https://api.mail.tm/domains", timeout=15)
            resp.raise_for_status()
            js = resp.json()
            items = js.get("hydra:member") or []
            return [it.get("domain") for it in items if it.get("domain")]
        except Exception:
            return []
    
    def generate_random_email(self, length: int = 10) -> str:
        """Generate random email address"""
        if self.provider == "1secmail":
            domains = self.get_available_domains()
            # If provider blocks or no domains, switch to mail.tm
            if not domains or self.last_http_status == 403:
                self.provider = "mailtm"
            else:
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
                domain = random.choice(domains)
                self.login = username
                self.domain = domain
                self.email = f"{username}@{domain}"
                return self.email
        # mail.tm account-based
        return self._mailtm_create_account()
    
    def generate_custom_email(self, username: str, domain: Optional[str] = None) -> str:
        """Generate custom email with specific username"""
        if self.provider == "1secmail":
            if not domain:
                domains = self.get_available_domains()
                domain = domains[0] if domains else "1secmail.com"
            self.login = username
            self.domain = domain
            self.email = f"{username}@{domain}"
            return self.email
        # mail.tm: try to create account with desired local and domain
        return self._mailtm_create_account(custom_local=username, domain=domain)
    
    def get_inbox(self) -> List[Dict]:
        """Get all emails from inbox"""
        if not self.login or not self.domain:
            print("❌ Please generate an email first!")
            return []
        
        # Rate limit provider polling
        now = time.time()
        if now - self._last_inbox_ts < self._min_fetch_interval_sec:
            return list(self._last_inbox)

        if self.provider == "1secmail":
            data = self._get_json(
                f"{self.base_url}?action=getMessages&login={self.login}&domain={self.domain}"
            )
            if isinstance(data, list):
                self._last_inbox = data
                self._last_inbox_ts = now
                return list(self._last_inbox)
            # If 1secmail is blocking, auto-switch to mail.tm and try once
            if self.last_http_status == 403:
                self.provider = "mailtm"
                # Ensure account exists
                if not self.mailtm_token:
                    self._mailtm_ensure_token()
                # Fall through to mail.tm branch below
        else:
            try:
                if not self.mailtm_token:
                    self._mailtm_ensure_token()
                headers = {"Authorization": f"Bearer {self.mailtm_token}"}
                resp = requests.get("https://api.mail.tm/messages", headers=headers, timeout=15)
                self.last_http_status = resp.status_code
                resp.raise_for_status()
                js = resp.json()
                items = js.get("hydra:member") or []
                normalized = []
                for it in items:
                    normalized.append({
                        'id': it.get('id'),
                        'from': (it.get('from') or {}).get('address'),
                        'subject': it.get('subject'),
                        'date': it.get('receivedAt')
                    })
                self._last_inbox = normalized
                self._last_inbox_ts = now
                return list(self._last_inbox)
            except Exception as e:
                self.last_http_error = str(e)
        if self.last_http_status == 403:
            print("❌ Error fetching inbox: Access forbidden (403). Try waiting a moment or generating a new email.")
        else:
            print("❌ Error fetching inbox: Provider returned no JSON list")
        # On error, return last cached inbox if available
        return list(self._last_inbox)
    
    def read_email(self, email_id: int) -> Dict:
        """Read specific email by ID"""
        if not self.login or not self.domain:
            print("❌ Please generate an email first!")
            return {}
        
        if self.provider == "1secmail":
            data = self._get_json(
                f"{self.base_url}?action=readMessage&login={self.login}&domain={self.domain}&id={email_id}"
            )
            if isinstance(data, dict):
                return data
        else:
            try:
                if not self.mailtm_token:
                    self._mailtm_ensure_token()
                headers = {"Authorization": f"Bearer {self.mailtm_token}"}
                resp = requests.get(f"https://api.mail.tm/messages/{email_id}", headers=headers, timeout=15)
                self.last_http_status = resp.status_code
                resp.raise_for_status()
                it = resp.json()
                body = it.get('text') or it.get('intro') or ''
                return {
                    'id': it.get('id'),
                    'from': (it.get('from') or {}).get('address'),
                    'subject': it.get('subject'),
                    'date': it.get('receivedAt'),
                    'textBody': body,
                    'body': body,
                }
            except Exception as e:
                self.last_http_error = str(e)
        print("❌ Error reading email: Provider returned no JSON object")
        return {}

    # ---------- mail.tm helpers ----------
    def _mailtm_create_account(self, custom_local: Optional[str] = None, domain: Optional[str] = None) -> str:
        try:
            # Get domain list
            doms = []
            try:
                resp = requests.get("https://api.mail.tm/domains", timeout=15)
                resp.raise_for_status()
                js = resp.json()
                doms = [it.get('domain') for it in (js.get('hydra:member') or []) if it.get('domain')]
            except Exception:
                pass
            use_domain = domain or (doms[0] if doms else None)

            local = custom_local or ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            address = f"{local}@{use_domain}" if use_domain else None
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

            # Create account
            create_payload = {"address": address, "password": password}
            resp = requests.post("https://api.mail.tm/accounts", json=create_payload, timeout=20)
            resp.raise_for_status()
            acc = resp.json()

            # Login to get token
            token_resp = requests.post("https://api.mail.tm/token", json={"address": acc.get("address"), "password": password}, timeout=20)
            token_resp.raise_for_status()
            tok = token_resp.json()

            self.mailtm_token = tok.get("token")
            self.mailtm_address = acc.get("address")
            self.mailtm_account_id = acc.get("id")
            self.email = self.mailtm_address
            self.login = self.mailtm_address.split('@')[0] if self.mailtm_address else None
            self.domain = self.mailtm_address.split('@')[1] if self.mailtm_address and '@' in self.mailtm_address else None
            self.provider = "mailtm"
            return self.email
        except Exception as e:
            print(f"❌ mail.tm error: {e}")
            # fall back to 1secmail
            self.provider = "1secmail"
            return self._fallback_1secmail_random()

    def _fallback_1secmail_random(self) -> str:
        domains = ["1secmail.com", "1secmail.org", "1secmail.net"]
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        domain = random.choice(domains)
        self.login = username
        self.domain = domain
        self.email = f"{username}@{domain}"
        return self.email
    
    def extract_codes(self, text: str) -> List[str]:
        """Extract verification codes/OTPs from email text"""
        patterns = [
            r'\b\d{4,8}\b',  # 4-8 digit codes
            r'\b[A-Z0-9]{4,8}\b',  # Alphanumeric codes
            r'code[:\s]+([A-Z0-9]{4,8})',  # "code: XXXX"
            r'OTP[:\s]+(\d{4,8})',  # "OTP: 1234"
            r'verification code[:\s]+([A-Z0-9]{4,8})',
            r'pin[:\s]+(\d{4,6})',  # PIN codes
        ]
        
        codes = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            codes.extend(matches)
        
        # Remove duplicates and return unique codes
        return list(set(codes))
    
    def wait_for_email(self, timeout: int = 60, check_interval: int = 5) -> Optional[Dict]:
        """Wait for new email with timeout"""
        print(f"⏳ Waiting for email (timeout: {timeout}s)...")
        
        start_time = time.time()
        last_count = 0
        
        while time.time() - start_time < timeout:
            inbox = self.get_inbox()
            
            if len(inbox) > last_count:
                print(f"📧 New email received!")
                return inbox[0]  # Return latest email
            
            last_count = len(inbox)
            time.sleep(check_interval)
            print(".", end="", flush=True)
        
        print("\n⏰ Timeout! No email received.")
        return None
    
    def display_email(self, email_data: Dict):
        """Display email in formatted way"""
        print("\n" + "="*60)
        print(f"📧 From: {email_data.get('from', 'Unknown')}")
        print(f"📌 Subject: {email_data.get('subject', 'No Subject')}")
        print(f"📅 Date: {email_data.get('date', 'Unknown')}")
        print("="*60)
        
        body = email_data.get('textBody') or email_data.get('body', '')
        print(f"\n{body}\n")
        
        # Extract and display codes
        codes = self.extract_codes(body)
        if codes:
            print("🔑 Detected Codes:")
            for i, code in enumerate(codes, 1):
                print(f"   {i}. {code}")
        
        print("="*60 + "\n")

    def save_email_to_file(self, email_data: Dict, output_dir: str = "inbox") -> str:
        """Save a single email to a text file and return the file path."""
        output_dir = self._ensure_output_dir(output_dir)

        email_from = email_data.get('from', 'Unknown')
        subject = email_data.get('subject', 'No Subject')
        date_str = email_data.get('date') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        body = email_data.get('textBody') or email_data.get('body', '')

        # Build filename
        # Normalize date for filename
        date_for_filename = re.sub(r"[^0-9]", "", datetime.now().strftime('%Y%m%d%H%M%S'))
        email_id_part = str(email_data.get('id') or "")
        subject_part = self._sanitize_filename(subject)[:60]
        filename = f"{date_for_filename}_{email_id_part}_{subject_part}.txt" if email_id_part else f"{date_for_filename}_{subject_part}.txt"
        file_path = os.path.join(output_dir, filename)

        content_lines = [
            f"From: {email_from}",
            f"Subject: {subject}",
            f"Date: {date_str}",
            "",
            "Message:",
            body or "(no body)",
            "",
        ]

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(content_lines))

        # Append to summary log
        summary_path = os.path.join(output_dir, "inbox_summary.txt")
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write(f"{filename}\t{date_str}\t{email_from}\t{subject}\n")

        return file_path

    def export_inbox(self, output_dir: str = "inbox") -> List[str]:
        """Export all current inbox emails to text files. Returns list of file paths."""
        exported_files: List[str] = []
        inbox = self.get_inbox()
        if not inbox:
            return exported_files

        output_dir = self._ensure_output_dir(output_dir)
        for item in inbox:
            try:
                email_id = item.get('id')
                email_data = self.read_email(email_id) if email_id is not None else item
                path = self.save_email_to_file(email_data, output_dir)
                exported_files.append(path)
            except Exception as e:
                # Skip problematic email but continue others
                print(f"❌ Failed to save email {item.get('id')}: {e}")
        return exported_files


class TempMailCLI:
    """Command Line Interface for Temp Mail"""
    
    def __init__(self):
        self.mail = TempMailGenerator()
    
    def run(self):
        """Run the CLI application"""
        print("\n" + "="*60)
        print("🚀 Advanced Temp Mail Generator".center(60))
        print("="*60 + "\n")
        
        while True:
            print("\n📋 Menu:")
            print("1. 🆕 Generate Random Email")
            print("2. ✏️  Generate Custom Email")
            print("3. 📬 Check Inbox")
            print("4. ⏳ Wait for Email (with timeout)")
            print("5. 📧 Read Specific Email")
            print("6. 🔑 Extract Codes from Last Email")
            print("7. 🌐 Show Available Domains")
            print("8. 🔄 Auto-Monitor Inbox")
            print("9. 🚪 Exit")
            print("10. 💾 Export Inbox to Files")
            
            choice = input("\n👉 Enter your choice: ").strip()
            
            if choice == '1':
                self.generate_random()
            elif choice == '2':
                self.generate_custom()
            elif choice == '3':
                self.check_inbox()
            elif choice == '4':
                self.wait_for_email()
            elif choice == '5':
                self.read_specific_email()
            elif choice == '6':
                self.extract_codes_from_last()
            elif choice == '7':
                self.show_domains()
            elif choice == '8':
                self.auto_monitor()
            elif choice == '9':
                print("\n👋 Bye! Thanks for using Temp Mail Generator!")
                break
            elif choice == '10':
                self.export_inbox_to_files()
            else:
                print("❌ Invalid choice! Please try again.")
    
    def generate_random(self):
        email = self.mail.generate_random_email()
        print(f"\n✅ Generated Email: {email}")
        print("📋 Use this email for registrations!")
    
    def generate_custom(self):
        username = input("Enter username: ").strip()
        domains = self.mail.get_available_domains()
        print("\nAvailable domains:")
        for i, domain in enumerate(domains[:5], 1):
            print(f"{i}. {domain}")
        
        choice = input("Choose domain (1-5) or press Enter for default: ").strip()
        domain = domains[int(choice)-1] if choice.isdigit() and 1 <= int(choice) <= 5 else None
        
        email = self.mail.generate_custom_email(username, domain)
        print(f"\n✅ Generated Email: {email}")
    
    def check_inbox(self):
        if not self.mail.email:
            print("❌ Please generate an email first!")
            return
        
        print(f"\n📬 Checking inbox for: {self.mail.email}")
        inbox = self.mail.get_inbox()
        
        if not inbox:
            print("📭 No emails yet!")
            return
        
        print(f"\n✉️  You have {len(inbox)} email(s):\n")
        for i, email in enumerate(inbox, 1):
            print(f"{i}. From: {email.get('from')}")
            print(f"   Subject: {email.get('subject')}")
            print(f"   Date: {email.get('date')}")
            print()
    
    def wait_for_email(self):
        timeout = int(input("Enter timeout in seconds (default 60): ").strip() or "60")
        email = self.mail.wait_for_email(timeout=timeout)
        
        if email:
            email_data = self.mail.read_email(email['id'])
            self.mail.display_email(email_data)
    
    def read_specific_email(self):
        inbox = self.mail.get_inbox()
        if not inbox:
            print("📭 No emails in inbox!")
            return
        
        self.check_inbox()
        email_num = int(input("Enter email number to read: ").strip())
        
        if 1 <= email_num <= len(inbox):
            email_data = self.mail.read_email(inbox[email_num-1]['id'])
            self.mail.display_email(email_data)
        else:
            print("❌ Invalid email number!")
    
    def extract_codes_from_last(self):
        inbox = self.mail.get_inbox()
        if not inbox:
            print("📭 No emails in inbox!")
            return
        
        email_data = self.mail.read_email(inbox[0]['id'])
        body = email_data.get('textBody') or email_data.get('body', '')
        codes = self.mail.extract_codes(body)
        
        if codes:
            print("\n🔑 Extracted Codes:")
            for i, code in enumerate(codes, 1):
                print(f"{i}. {code}")
        else:
            print("❌ No codes found in the email!")
    
    def show_domains(self):
        domains = self.mail.get_available_domains()
        print("\n🌐 Available Domains:")
        for i, domain in enumerate(domains, 1):
            print(f"{i}. {domain}")
    
    def auto_monitor(self):
        """Auto monitor inbox for new emails"""
        print("\n🔄 Auto-monitoring started...")
        print("📧 Current email:", self.mail.email)
        print("Press Ctrl+C to stop\n")
        
        last_count = 0
        try:
            while True:
                inbox = self.mail.get_inbox()
                
                if len(inbox) > last_count:
                    print("\n🔔 New email detected!")
                    new_emails = inbox[:len(inbox) - last_count]
                    
                    for email in new_emails:
                        email_data = self.mail.read_email(email['id'])
                        self.mail.display_email(email_data)
                
                last_count = len(inbox)
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped!")

    def export_inbox_to_files(self):
        output_dir = input("Enter output folder (default 'inbox'): ").strip() or "inbox"
        files = self.mail.export_inbox(output_dir)
        if files:
            print(f"\n✅ Saved {len(files)} email(s) to '{output_dir}'.")
            print(f"📄 Summary log: {os.path.join(output_dir, 'inbox_summary.txt')}")
        else:
            print("📭 No emails to export!")


# Example usage as a module
if __name__ == "__main__":
    # Run CLI
    cli = TempMailCLI()
    cli.run()
    
    # Or use as module:
    # mail = TempMailGenerator()
    # email = mail.generate_random_email()
    # print(f"Generated: {email}")
    # inbox = mail.get_inbox()
