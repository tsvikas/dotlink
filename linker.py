"""Softlink Installation Utility

This module provides functionality to safely install softlinks (symbolic links)
to a list of files and directories while preserving backups of any existing
files. It's particularly useful for managing dotfiles or other configuration
files that need to be linked from a central location to various places in the
filesystem.

Features:
- Read link specifications from TOML configuration files
- Create softlinks while safely backing up existing files
- Remove files (with backup) when needed
- Provide various levels of verbosity for operation feedback

Example usage:
    # From command line:
    ``` bash
    $ python softlink_installer.py ~/my-dotfiles
    $ python softlink_installer.py ~/my-dotfiles -d /custom/install/path -qq
    ```

    # As a module:
    ```python
    from pathlib import Path
    from softlink_installer import install_links

    locations = {Path.home() / ".config/app": Path.home() / "dotfiles/app"}
    install_links(locations)
    ```

Configuration:
    The locations.toml file should be structured as follows:
    ```toml
    # Link destination = Link source (relative to toml file location)
    ".bashrc" = "rcfiles/bashrc"
    ".config/app" = "config_folder_for_app"
    ".local/bin/my-script" = "my-script.py"
    # Empty string means remove the file (with backup)
    ".oldfile" = ""
    ```

Notes:
    - All paths in the TOML file are relative to either the installation base
      directory (destinations) or the TOML file's parent directory (sources)
    - Existing files at destination paths are automatically backed up with
      .bkp_N suffixes where N is an incrementing number

"""

import argparse
import enum
import tomllib
from itertools import count
from pathlib import Path


class VerboseLevel(enum.IntEnum):
    """Enumeration of verbosity levels for operation feedback.

    Attributes:
        NOTHING (0): No output
        RENAME_FILE (1): Show file rename operations
        CREATE_LINK (2): Show as above, plus link creation operations.
        LINK_OK (3): Show as above, plus specify already existing links.

    """

    NOTHING = 0
    RENAME_FILE = 1
    CREATE_LINK = 2
    LINK_OK = 3


MAX_VERBOSE = max(VerboseLevel)


def safe_remove(p: Path, verbose_level: VerboseLevel) -> Path:
    """Safely rename a file or directory to a backup name.

    Creates a backup by appending .bkp_N to the filename, where N is an incrementing
    number starting from 0, continuing until an unused name is found.

    Args:
        p: Path to the file or directory to be renamed
        verbose_level: Controls the amount of feedback printed during operation

    Returns:
        Path: The new path where the file/directory was moved to

    """
    if not p.is_absolute():
        raise ValueError(f"{p} is not absolute")
    if not p.exists(follow_symlinks=False):
        raise ValueError(f"{p} does not exist")
    for i in count():
        p_backup = Path(f"{p}.bkp_{i}")
        if not p_backup.exists(follow_symlinks=False):
            break
    if verbose_level >= VerboseLevel.RENAME_FILE:
        print(f"renaming {p} -> {p_backup}")
    p.rename(p_backup)
    if p.exists(follow_symlinks=False):
        raise RuntimeError(f"failed to move file: {p}")
    return p_backup


def safe_link(src: Path, dst: Path, verbose_level: VerboseLevel) -> None:
    """Create a symbolic link from dst to src, safely handling existing files.

    If dst already exists, it will be backed up using safe_remove() before
    creating the new link, unless dst is already a correct symlink to src,
    in which case no action is taken.

    Args:
        src: Path to the source file/directory to link to
        dst: Path where the symbolic link should be created
        verbose_level: Controls the amount of feedback printed during operation

    """
    if not dst.is_absolute():
        raise ValueError(f"{dst} is not absolute")
    if not src.is_absolute():
        raise ValueError(f"{src} is not absolute")
    is_dir = "/" if src.is_dir() else ""
    if not src.exists(follow_symlinks=True):
        # TODO: maybe here i want to mv dst -> src instead?
        raise ValueError(f"src {src} not found")
    if dst.is_symlink() and dst.readlink() == src:
        if verbose_level >= VerboseLevel.LINK_OK:
            print(f"exists   {dst} <- {src}{is_dir}")
        return
    if dst.exists(follow_symlinks=False):
        safe_remove(dst, verbose_level)
    if verbose_level >= VerboseLevel.CREATE_LINK:
        print(f"linking  {dst} <- {src}{is_dir}")
    dst.parent.mkdir(exist_ok=True, parents=True)
    dst.symlink_to(src)


def install_links(
    locations: dict[Path, Path | None],
    verbose_level: VerboseLevel = MAX_VERBOSE,
) -> None:
    """Install symbolic links according to the locations dictionary.

    For each entry in locations, creates a symbolic link from the destination
    (key) to the source (value). If the value is None, the destination file
    is removed (with backup).

    Args:
        locations: Dictionary mapping destination paths to source paths
        verbose_level: Controls the amount of feedback printed

    """
    for dst, src in locations.items():
        if src is None:
            if dst.exists(follow_symlinks=False):
                safe_remove(dst, verbose_level)
        else:
            safe_link(src, dst, verbose_level)


def read_locations_file(
    toml_file: Path,
    src_dir: Path,
    dst_dir: Path = Path.home(),  # noqa: B008
    *,
    allow_linking_outside_dst_dir: bool = False,
    fail_if_relative_dst: bool = False,
    fail_if_absolute_dst: bool = False,
) -> dict[Path, Path | None]:
    """Read link specifications from a TOML file.

    The TOML file should contain key-value pairs where:
    - Keys are destination paths (relative to dst_dir)
    - Values are source paths (relative to src_dir) or "" to remove

    Args:
        toml_file: Path to the TOML configuration file
        src_dir: Base directory containing source files
        dst_dir: Base directory where links will be created (default: user's home)

    Returns:
        Dictionary mapping destination Paths to source Paths or None

    Example TOML content:
        ```toml
        ".bashrc" = "rcfiles/bashrc"
        ".config/app" = "config_folder_for_app"
        ".local/bin/my-script" = "my-script.py"
        ".oldfile" = ""
        ```
    """
    if fail_if_relative_dst and fail_if_absolute_dst:
        raise ValueError("Can't require both relative and absolute")
    with Path(toml_file).open("rb") as f:
        data = tomllib.load(f)
    locations = {Path(dst): Path(src) if src else None for dst, src in data.items()}
    # check dst
    if fail_if_relative_dst and any(not dst.is_absolute() for dst in locations):
        raise ValueError("settings require all dst must be absolute")
    if fail_if_absolute_dst and any(dst.is_absolute() for dst in locations):
        raise ValueError("settings require all dst must be relative")
    # check src
    if any(src is not None and src.is_absolute() for src in locations.values()):
        raise ValueError("all src must be relative")
    # resolve locations
    dst_dir = dst_dir.absolute()
    src_dir = src_dir.absolute()
    locations_full = {
        dst_dir / dst.expanduser(): None if src is None else src_dir / src
        for dst, src in locations.items()
    }
    # check parents
    if not allow_linking_outside_dst_dir and not all(
        dst_dir in dst.parents for dst in locations_full
    ):
        raise ValueError(f"settings require all dst must be inside {dst_dir}")
    if not all(
        src is None or src_dir in src.parents for src in locations_full.values()
    ):
        # this should never fail, since we checked that all src in locations are
        #  relative
        raise ValueError(f"all src must be inside {src_dir}")
    # result
    return locations_full


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="install links to a list of files")
    parser.add_argument(
        "SRC_DIR",
        help="Path containing the targets. Must contain `locations.toml`. "
        "default: user home dir",
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
        help="Increase quietness level "
        f"(can be repeated up to {int(MAX_VERBOSE)} times)",
    )
    return parser.parse_args()


def main() -> None:
    """Command-line interface for the link installer.

    Provides a command-line interface to read a locations.toml file and install
    the specified links. The source directory must contain a locations.toml file
    specifying the links to create.

    Command-line Arguments:
        SRC_DIR: Directory containing source files and locations.toml
        -d/--dest_dir: Directory to install links into (default: home directory)
        -q/--quiet: Reduce verbosity (can be specified multiple times)
    """
    args = parse_args()
    src_dir = args.SRC_DIR
    dst_dir = args.dest_dir
    verbose_level = VerboseLevel(MAX_VERBOSE - args.quiet)
    locations = read_locations_file(src_dir / "locations.toml", src_dir, dst_dir)
    install_links(locations, verbose_level)


if __name__ == "__main__":
    main()
