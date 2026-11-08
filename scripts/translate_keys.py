"""Install the translation API keys on this machine (the owner, 2026-11-08): the operator writes the keys into a file
anywhere (e.g. ~/Desktop/translate.keys), this script moves it to the keys' place outside the repo, makes it 0600
and writes its path into the repo-root .env (TRANSLATE_KEY_FILE). Nothing is printed but the key names found.

    .venv/bin/python scripts/translate_keys.py install ~/Desktop/translate.keys
    .venv/bin/python scripts/translate_keys.py check

The file the operator writes (plain text, one key per line, either may be left out):
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-...

Its place: ~/.config/naver-shopping-scraper/translate.keys (outside the repo, so git never sees it).
"""
import argparse
import os
import shutil
import sys
import tempfile

from naver_api_client import ENV_FILE
from translate import ANTHROPIC_KEY, KEY_FILE_ENV, OPENAI_KEY, TranslateError, read_keys

KEYS_HOME = os.path.join(os.path.expanduser("~"), ".config", "naver-shopping-scraper")
KEYS_FILE = os.path.join(KEYS_HOME, "translate.keys")
PREFIXES = {ANTHROPIC_KEY: "sk-ant-", OPENAI_KEY: "sk-"}


def looks_right(keys: dict[str, str]) -> list[str]:
    """The keys whose start is not their provider's (a key pasted into the wrong line); values never shown."""
    return [name for name, key in keys.items() if not key.startswith(PREFIXES[name])
            or (name == OPENAI_KEY and key.startswith("sk-ant-"))]


def set_env(env_file: str, name: str, value: str) -> None:
    """name=value in the .env file: the line replaced if there, else appended; the file stays 0600."""
    lines: list[str] = []
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, done = [], False
    for line in lines:
        if line.strip().removeprefix("export ").split("=", 1)[0].strip() == name:
            if not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{name}={value}")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(env_file)), prefix=".env.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, env_file)


def install(source: str, target: str = KEYS_FILE, env_file: str = ENV_FILE) -> list[str]:
    """The operator's file -> target (moved, 0600), its path into .env. Returns the key names found."""
    source = os.path.realpath(os.path.expanduser(source))
    if not os.path.isfile(source):
        raise TranslateError(f"{source} does not exist")
    os.chmod(source, 0o600)
    keys = read_keys(source, ignored=lambda p: True)             # the file is moved out of any repo next
    wrong = looks_right(keys)
    if wrong:
        raise TranslateError(f"these keys do not look like their provider's ({', '.join(wrong)}): check the lines")
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    if os.path.realpath(target) != source:
        shutil.move(source, target)
    os.chmod(target, 0o600)
    set_env(env_file, KEY_FILE_ENV, target)
    return sorted(keys)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Install or check the translation API keys (values never printed).")
    p.add_argument("command", choices=("install", "check"))
    p.add_argument("file", nargs="?", help="install: the file the operator wrote the keys into")
    args = p.parse_args(argv)
    try:
        if args.command == "install":
            if not args.file:
                p.error("install needs the file")
            names = install(args.file)
            print(f"installed {KEYS_FILE} (0600): {', '.join(names)}; {KEY_FILE_ENV} set in {ENV_FILE}")
        else:
            path = os.environ.get(KEY_FILE_ENV) or KEYS_FILE
            keys = read_keys(path)
            wrong = looks_right(keys)
            print(f"{path}: {', '.join(sorted(keys))}" + (f"; check {', '.join(wrong)}" if wrong else "; ok"))
            if wrong:
                return 1
    except TranslateError as e:
        print(f"translate_keys: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
