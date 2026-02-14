import pymysql
import bcrypt
import os

class AuthDatabase:
    def __init__(self):
        # Update these credentials according to your MySQL setup
        self.host = os.getenv("DB_HOST", "127.0.0.1")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "2345")
        self.db_name = os.getenv("DB_NAME", "user")

    def get_connection(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.db_name,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )

    def setup_database(self):
        """Creates the database and users table if they don't exist."""
        try:
            conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
        except pymysql.err.OperationalError as e:
            print(f"\n[!] Connection Failed. User: {self.user}, Host: {self.host}, Port: {self.port}")
            print(f"[!] Please verify your password in MySQL Workbench.")
            raise e

        try:
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name}")
            
            conn.select_db(self.db_name)
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        email VARCHAR(100) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        otp VARCHAR(6),
                        otp_expiry TIMESTAMP NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Check if otp column exists (for existing tables)
                cursor.execute("SHOW COLUMNS FROM users LIKE 'otp'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN otp VARCHAR(6)")
                    cursor.execute("ALTER TABLE users ADD COLUMN otp_expiry TIMESTAMP NULL")
                    print("Migrated database: Added otp columns.")

                print("Database and tables checked/created successfully.")
        finally:
            conn.close()

    def register_user(self, username, email, password):
        """Hashes password and saves user to database."""
        # Hash the password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)"
                cursor.execute(sql, (username, email, hashed_password.decode('utf-8')))
                return {"status": "SUCCESS", "message": "User registered successfully"}
        except pymysql.IntegrityError as e:
            return {"status": "ERROR", "message": "Username or Email already exists"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
        finally:
            conn.close()

    def verify_user(self, username, password):
        """Checks if username exists and password matches."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM users WHERE username = %s"
                cursor.execute(sql, (username,))
                user = cursor.fetchone()

                if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                    return {"status": "SUCCESS", "user_id": user['id'], "message": "Login successful"}
                else:
                    return {"status": "ERROR", "message": "Invalid credentials"}
        finally:
            conn.close()

    def save_otp(self, email, otp):
        """Saves an OTP for a user with a 10-minute expiry."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Check if user exists
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if not cursor.fetchone():
                    return {"status": "ERROR", "message": "User not found"}

                # Update OTP (valid for 10 minutes)
                sql = "UPDATE users SET otp = %s, otp_expiry = DATE_ADD(NOW(), INTERVAL 10 MINUTE) WHERE email = %s"
                cursor.execute(sql, (otp, email))
                return {"status": "SUCCESS", "message": "OTP generated"}
        finally:
            conn.close()

    def reset_password_with_otp(self, email, otp, new_password):
        """Verifies OTP and updates the password."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Verify OTP and Expiry
                sql = "SELECT id FROM users WHERE email = %s AND otp = %s AND otp_expiry > NOW()"
                cursor.execute(sql, (email, otp))
                user = cursor.fetchone()

                if not user:
                    return {"status": "ERROR", "message": "Invalid or expired OTP"}

                # Hash new password
                salt = bcrypt.gensalt()
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), salt)

                # Update password and clear OTP
                update_sql = "UPDATE users SET password_hash = %s, otp = NULL, otp_expiry = NULL WHERE id = %s"
                cursor.execute(update_sql, (hashed_password.decode('utf-8'), user['id']))
                return {"status": "SUCCESS", "message": "Password updated successfully"}
        finally:
            conn.close()

    def check_email_exists(self, email):
        """Checks if an email exists in the database."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT id FROM users WHERE email = %s"
                cursor.execute(sql, (email,))
                return cursor.fetchone() is not None
        finally:
            conn.close()