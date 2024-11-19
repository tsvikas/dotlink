"""install softlinks to a list of files.

safely replaces all local files with a softlink to these files.
"""

import argparse
import enum
import tomllib
from itertools import count
from pathlib import Path


class VerboseLevel(enum.IntEnum):
    NOTHING = 0
    RENAME_FILE = 1
    CREATE_LINK = 2
    LINK_OK = 3


def safe_remove(p: Path, verbose_level: VerboseLevel) -> Path:
    """Rename `p` to an unused name. Works with files and directories."""
    p = p.absolute()
    assert p.exists(follow_symlinks=False)
    for i in count():
        p_backup = Path(f"{p}.bkp_{i}")
        if not p_backup.exists(follow_symlinks=False):
            break
    if verbose_level >= VerboseLevel.RENAME_FILE:
        print(f"renaming {p} -> {p_backup}")
    p.rename(p_backup)
    assert not p.exists(follow_symlinks=False)
    return p_backup


def safe_link(src: Path, dst: Path, verbose_level: VerboseLevel) -> None:
    """Replace `dst` with a link to `src`, and save a backup of `dst`."""
    src = src.absolute()
    dst = dst.absolute()
    if not src.exists(follow_symlinks=True):
        # TODO: maybe here i want to mv dst -> src instead?
        raise ValueError(f"src {src} not fount")
    if dst.is_symlink() and dst.readlink() == src:
        if verbose_level >= VerboseLevel.LINK_OK:
            print(f"exists   {dst} <- {src}")
        return
    if dst.exists(follow_symlinks=False):
        safe_remove(dst)
    if verbose_level >= VerboseLevel.CREATE_LINK:
        print(f"linking  {dst} <- {src}")
    dst.parent.mkdir(exist_ok=True, parents=True)
    dst.symlink_to(src)


def install_links(
    locations: dict[Path, Path | None],
    src_dir: Path,
    dst_dir: Path = Path.home(),
    verbose_level: VerboseLevel = max(VerboseLevel),
) -> None:
    """Install all links in locations

    locations is a dict of `dst: src` items, and each dst will be a link to src.
    if src is None, dst will be removed
    """
    for dst, src in locations.items():
        # find dst
        dst = dst_dir / dst.expanduser()
        if dst_dir not in dst.parents:
            raise ValueError(f"only linking files into {dst_dir}, not {dst}")
        # remove it
        if src is None:
            if dst.exists(follow_symlinks=False):
                safe_remove(dst, verbose_level)
            return
        # or link it
        src = src_dir / src
        if dst_dir not in dst.parents:
            raise ValueError(f"only linking files from {src_dir}, not {src}")
        safe_link(src_dir / src, dst, verbose_level)


def read_locations_file(toml_file: Path) -> dict[Path, Path | None]:
    """Read a locations toml file and return dict of Path objects"""
    data = tomllib.load(Path(toml_file).open("rb"))
    return {Path(dst): Path(src) if src else None for dst, src in data.items()}


def main() -> None:
    """CLI for install_links"""
    parser = argparse.ArgumentParser(description="install links to a list of files")
    parser.add_argument(
        "SRC_DIR",
        help="Path containing the targets. Must contain `locations.toml`. default: user home dir",
        type=Path,
    )
    parser.add_argument(
        "-d",
        "--dest_dir",
        help="Path to install the links into",
        type=Path,
        default=Path.home(),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help=f"Increase quietness level (can be repeated up to {int(max(VerboseLevel))} times)",
    )
    args = parser.parse_args()
    src_dir = args.SRC_DIR
    locations = read_locations_file(src_dir / "locations.toml")
    dst_dir = args.dest_dir
    verbose_level = VerboseLevel(max(VerboseLevel) - args.quiet)
    install_links(locations, src_dir, dst_dir, verbose_level)


if __name__ == "__main__":
    main()
