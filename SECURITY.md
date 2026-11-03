"""SecureVault - an encrypted desktop vault for your accounts and passwords."""
import sys

USAGE = """SecureVault options:
  --minimized   start hidden in the system tray
  --quit        ask a running SecureVault to close
  --version     print the version"""


def main() -> None:
    args = {a.lower() for a in sys.argv[1:]}
    if "--version" in args:
        from vault import __version__
        print(__version__)
        return
    if "--help" in args or "-h" in args:
        print(USAGE)
        return
    try:
        from vault.instance import SingleInstance
        from vault.settings import data_dir
    except ImportError as exc:  # missing dependency
        print(f"Missing dependency: {exc}\nRun:  pip install -r requirements.txt")
        sys.exit(1)
    instance = SingleInstance(str(data_dir()))
    if "--quit" in args:                # close the running copy and exit
        instance.notify_existing("quit")
        return
    if not instance.acquire():          # already running: bring that window to the front and quit
        instance.notify_existing("open")
        return
    from vault.ui.app import VaultApp
    VaultApp(instance=instance, start_hidden="--minimized" in args).mainloop()


if __name__ == "__main__":
    main()
