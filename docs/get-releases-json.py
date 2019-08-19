#!/usr/bin/env python3

import json
import subprocess

from distutils.version import StrictVersion


def get_versions():

    output = subprocess.check_output(
        ["git", "tag", "-l", "--format=%(creatordate:iso-strict)|%(refname:short)"]
    )
    tags = []

    for line in output.decode().splitlines():
        try:
            date, tag = line.split("|")
        except (ValueError):
            continue

        if not date or not tag:
            continue

        tags.append({"id": tag, "date": date})
    valid = []
    for tag in tags:
        try:
            StrictVersion(tag["id"])
            valid.append(tag)
        except ValueError:
            continue

    return sorted(valid, key=lambda tag: StrictVersion(tag["id"]), reverse=True)


def main():
    versions = get_versions()
    data = {"count": len(versions), "releases": versions}
    print(json.dumps(data))


if __name__ == "__main__":
    main()
