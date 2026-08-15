from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession, SQLiteSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
)


class SessionManager:
    def __init__(self, accounts_dir):
        self.accounts_dir = Path(accounts_dir)
        self.accounts_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.clients = {}
        self.phone_hashes = {}

    def _pending_path(self, phone):
        safe_phone = "".join(
            c for c in phone
            if c.isdigit()
        )
        return self.accounts_dir / f".pending_{safe_phone}"

    def _session_path(self, install_id):
        directory = (
            self.accounts_dir /
            str(install_id)
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return directory / "session"

    async def send_code(
        self,
        phone,
        api_id,
        api_hash,
    ):
        old_client = self.clients.pop(
            phone,
            None,
        )

        self.phone_hashes.pop(
            phone,
            None,
        )

        if old_client:
            try:
                await old_client.disconnect()
            except Exception:
                pass

        pending = self._pending_path(phone)

        for path in (
            pending,
            Path(str(pending) + ".session"),
        ):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        client = TelegramClient(
            str(pending),
            api_id,
            api_hash,
        )

        await client.connect()

        try:
            result = await client.send_code_request(
                phone
            )
        except Exception:
            await client.disconnect()
            raise

        self.clients[phone] = client
        self.phone_hashes[phone] = (
            result.phone_code_hash
        )

        return result

    async def resend_code(self, phone):
        client = self.clients.get(phone)

        if client is None:
            raise RuntimeError(
                "جلسة التحقق غير موجودة. "
                "ابدأ تسجيل الدخول من جديد."
            )

        if not client.is_connected():
            await client.connect()

        result = await client.send_code_request(
            phone
        )

        self.phone_hashes[phone] = (
            result.phone_code_hash
        )

        return result

    async def login_code(
        self,
        install_id,
        phone,
        code,
        api_id,
        api_hash,
        password=None,
    ):
        client = self.clients.get(phone)

        if client is None:
            raise RuntimeError(
                "جلسة التحقق غير موجودة."
            )

        if not client.is_connected():
            await client.connect()

        try:
            if password:
                await client.sign_in(
                    password=password
                )
            else:
                phone_code_hash = (
                    self.phone_hashes.get(phone)
                )

                if not phone_code_hash:
                    raise RuntimeError(
                        "كود التحقق غير موجود."
                    )

                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash,
                )

        except SessionPasswordNeededError:
            raise

        except PhoneCodeExpiredError:
            raise RuntimeError(
                "انتهت صلاحية الكود. "
                "أرسل كودًا جديدًا."
            )

        except PhoneCodeInvalidError:
            raise RuntimeError(
                "كود Telegram غير صحيح."
            )

        if not await client.is_user_authorized():
            raise RuntimeError(
                "فشل تسجيل الدخول للحساب."
            )

        client.session.save()

        pending_file = Path(
            str(self._pending_path(phone))
            + ".session"
        )

        target_file = Path(
            str(self._session_path(install_id))
            + ".session"
        )

        await client.disconnect()

        self.clients.pop(
            phone,
            None,
        )

        self.phone_hashes.pop(
            phone,
            None,
        )

        if not pending_file.exists():
            raise RuntimeError(
                "لم يتم إنشاء ملف جلسة Telegram."
            )

        target_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        pending_file.replace(
            target_file
        )

        return str(
            self._session_path(install_id)
        )

    async def install_string_session(
        self,
        install_id,
        session_string,
        api_id,
        api_hash,
    ):
        session_string = (
            session_string or ""
        ).strip()

        if not session_string:
            raise RuntimeError(
                "Session String فارغة."
            )

        client = None
        target = None

        try:
            client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash,
            )

            await client.connect()

            authorized = (
                await client.is_user_authorized()
            )

            if not authorized:
                raise RuntimeError(
                    "Session String غير صالحة "
                    "أو غير مسجلة الدخول."
                )

            source = client.session

            target_base = (
                self._session_path(install_id)
            )

            target_file = Path(
                str(target_base) + ".session"
            )

            target_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            # حذف Session قديمة إن وجدت
            if target_file.exists():
                target_file.unlink()

            # إنشاء SQLite Session جديدة
            target = SQLiteSession(
                str(target_base)
            )

            target.set_dc(
                source.dc_id,
                source.server_address,
                source.port,
            )

            target.auth_key = (
                source.auth_key
            )

            target.save()

            target.close()

            target = None

            if not target_file.exists():
                raise RuntimeError(
                    "فشل إنشاء ملف session."
                )

            return str(target_base)

        except RuntimeError:
            raise

        except Exception as error:
            raise RuntimeError(
                f"فشل تحويل Session String: {error}"
            )

        finally:
            if target is not None:
                try:
                    target.close()
                except Exception:
                    pass

            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    async def close(self):
        for phone, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass

        self.clients.clear()
        self.phone_hashes.clear()
