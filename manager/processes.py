import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


class ProcessManager:
    def __init__(self, template_dir, accounts_dir):
        self.template = Path(template_dir)
        self.accounts = Path(accounts_dir)

        self.accounts.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.procs = {}

    def path(self, install_id):
        return self.accounts / str(install_id)

    def create(self, install_id):
        if not self.template.exists():
            raise RuntimeError(
                f"Template not found: {self.template}"
            )

        destination = self.path(install_id)

        if destination.exists():
            shutil.rmtree(destination)

        shutil.copytree(
            self.template,
            destination,
        )

        return destination

    def find_session(self, directory):
        """
        البحث عن ملف Telethon SQLite Session
        داخل مجلد الحساب بالكامل.
        """

        # الاسم الأساسي المتوقع
        preferred = directory / "session.session"

        if preferred.is_file():
            return preferred

        # البحث داخل الحساب
        candidates = sorted(
            directory.rglob("*.session")
        )

        # استبعاد أي ملفات غير صالحة
        candidates = [
            path
            for path in candidates
            if path.is_file()
        ]

        if candidates:
            return candidates[0]

        return None

    def start(self, install_id):
        directory = self.path(install_id)

        if not directory.exists():
            raise RuntimeError(
                f"Account directory does not exist: {directory}"
            )

        # Tepthon يتم نسخه مباشرة داخل مجلد التنصيب
        package = directory

        if not (package / "__main__.py").exists():
            raise RuntimeError(
                f"__main__.py غير موجود داخل: {package}"
            )

        # البحث عن Session الخاصة بهذا التنصيب
        session_file = self.find_session(directory)

        if session_file is None:
            raise RuntimeError(
                f"Session غير موجودة للحساب {install_id}. "
                "سجّل الدخول أولاً من المصنع."
            )

        # إيقاف النسخة القديمة إن كانت تعمل
        self.stop(install_id)

        env = os.environ.copy()

        # معلومات المصنع
        env["FACTORY_INSTALL_ID"] = str(
            install_id
        )

        env["FACTORY_ACCOUNT_DIR"] = str(
            directory.absolute()
        )

        # Session الخاصة بالحساب
        session_path = str(
            session_file.absolute()
        )

        env["SESSION"] = session_path
        env["TEPTHON_SESSION"] = session_path

        # إعدادات Tepthon
        api_id = os.getenv("API_ID", "")
        api_hash = os.getenv("API_HASH", "")
        bot_token = os.getenv("BOT_TOKEN", "")
        owner_id = os.getenv("OWNER_ID", "")

        if api_id:
            env["API_ID"] = api_id

        if api_hash:
            env["API_HASH"] = api_hash

        if bot_token:
            env["BOT_TOKEN"] = bot_token

        if owner_id:
            env["OWNER_ID"] = owner_id

        # Redis
        env["REDISHOST"] = os.getenv(
            "REDISHOST",
            "127.0.0.1",
        )

        env["REDISPORT"] = os.getenv(
            "REDISPORT",
            "6379",
        )

        # لا نسمح لنسخة Tepthon بأخذ PORT
        # الخاص بالمصنع الرئيسي
        env.pop("PORT", None)

        # سجل خاص بكل تنصيب
        log_path = directory / "factory.log"

        log_file = open(
            log_path,
            "a",
            encoding="utf-8",
        )

        # معلومات تشخيصية
        log_file.write(
            "\n"
            "========================================\n"
            f"FACTORY INSTALL ID: {install_id}\n"
            f"ACCOUNT DIR: {directory.absolute()}\n"
            f"SESSION: {session_path}\n"
            "========================================\n"
        )

        log_file.flush()

        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import sys,types,importlib.util;"
                    "p='.';"
                    "m=types.ModuleType('Tepthon');"
                    "m.__path__=[p];"
                    "m.__package__='Tepthon';"
                    "sys.modules['Tepthon']=m;"
                    "spec=importlib.util.spec_from_file_location("
                    "'Tepthon.__main__','__main__.py');"
                    "mod=importlib.util.module_from_spec(spec);"
                    "sys.modules['Tepthon.__main__']=mod;"
                    "spec.loader.exec_module(mod)"
                ),
            ],
            cwd=directory,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        self.procs[install_id] = (
            process,
            log_file,
        )

        return process.pid

    def stop(self, install_id):
        item = self.procs.pop(
            install_id,
            None,
        )

        if not item:
            return

        process, log_file = item

        if process.poll() is None:
            try:
                os.killpg(
                    process.pid,
                    signal.SIGTERM,
                )
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass

            try:
                process.wait(timeout=8)

            except Exception:
                try:
                    os.killpg(
                        process.pid,
                        signal.SIGKILL,
                    )
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

        try:
            log_file.close()
        except Exception:
            pass

    def restart(self, install_id):
        self.stop(install_id)
        return self.start(install_id)

    def delete(self, install_id):
        self.stop(install_id)

        directory = self.path(install_id)

        if directory.exists():
            shutil.rmtree(directory)

    def log(self, install_id):
        log_path = self.path(install_id) / "factory.log"

        if not log_path.exists():
            return ""

        try:
            return log_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception as error:
            return f"Unable to read log: {error}"
