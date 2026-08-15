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

        package_destination = destination / "Tepthon"

        shutil.copytree(
            self.template,
            package_destination,
        )

        return destination

    def find_session(self, directory):
        preferred = directory / "session.session"

        if preferred.is_file():
            return preferred

        candidates = sorted(
            directory.rglob("*.session")
        )

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

        # Tepthon package داخل مجلد الحساب
        package = directory / "Tepthon"

        if not package.is_dir():
            raise RuntimeError(
                f"Tepthon package غير موجود داخل: {package}"
            )

        if not (package / "__main__.py").is_file():
            raise RuntimeError(
                f"__main__.py غير موجود داخل: {package}"
            )

        # البحث عن Session داخل مجلد الحساب
        session_file = self.find_session(directory)

        if session_file is None:
            raise RuntimeError(
                f"Session غير موجودة للحساب {install_id}. "
                "سجّل الدخول أولاً من المصنع."
            )

        # إيقاف النسخة القديمة
        self.stop(install_id)

        env = os.environ.copy()

        env["FACTORY_INSTALL_ID"] = str(
            install_id
        )

        env["FACTORY_ACCOUNT_DIR"] = str(
            directory.absolute()
        )

        # Python يجب أن يرى مجلد الحساب الذي يحتوي Tepthon/
        env["PYTHONPATH"] = (
            str(directory.absolute())
            + os.pathsep
            + env.get("PYTHONPATH", "")
        )

        session_path = str(
            session_file.absolute()
        )

        env["SESSION"] = session_path
        env["TEPTHON_SESSION"] = session_path

        # إعدادات Tepthon
        for key in (
            "API_ID",
            "API_HASH",
            "BOT_TOKEN",
            "OWNER_ID",
        ):
            value = os.getenv(key, "")
            if value:
                env[key] = value

        env["REDISHOST"] = os.getenv(
            "REDISHOST",
            "127.0.0.1",
        )

        env["REDISPORT"] = os.getenv(
            "REDISPORT",
            "6379",
        )

        # لا نسمح لنسخة Tepthon بأخذ PORT
        env.pop("PORT", None)

        # سجل خاص بكل تنصيب
        log_path = directory / "factory.log"

        log_file = open(
            log_path,
            "a",
            encoding="utf-8",
        )

        log_file.write(
            "\n"
            "========================================\n"
            f"FACTORY INSTALL ID: {install_id}\n"
            f"ACCOUNT DIR: {directory.absolute()}\n"
            f"TEPTHON DIR: {package.absolute()}\n"
            f"SESSION: {session_path}\n"
            "========================================\n"
        )

        log_file.flush()

        # تشغيل Tepthon كـ Python package
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "Tepthon",
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
