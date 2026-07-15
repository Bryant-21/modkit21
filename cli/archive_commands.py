"""modkit archive — native archive browsing and extraction commands."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import click

from cli._output import output


def _ctx_fmt(ctx) -> str:
    return ctx.obj.get("fmt", "json")


def _normalize_member_path(file_path: str) -> str:
    value = str(file_path).strip().replace("\\", "/")
    if not value:
        raise click.ClickException("Archive member path cannot be empty")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise click.ClickException(f"Unsafe archive member path: {file_path}")
    return str(pure).lower()


@click.group()
def archive():
    """Browse and extract BSA/BA2 archives."""


@archive.command("list")
@click.argument("archive_path")
@click.pass_context
def list_archive_cmd(ctx, archive_path: str):
    """Return archive metadata and file listing."""
    from creation_lib.ba2 import native_runtime

    archive = Path(archive_path).expanduser().resolve(strict=False)
    if not archive.is_file():
        raise click.ClickException(f"Archive not found: {archive}")

    files = native_runtime.list_archive(str(archive))
    info = dict(native_runtime.archive_info(str(archive)))
    info.update(
        {
            "path": str(archive),
            "archive_name": archive.name,
            "backend": "native",
        }
    )
    payload = dict(info)
    payload["file_count"] = len(files)
    payload["files"] = sorted(files)
    output(payload, _ctx_fmt(ctx))


@archive.command()
@click.argument("archive_path")
@click.argument("file_path")
@click.option(
    "--output-dir",
    required=True,
    help="Destination directory. Relative archive folders are preserved.",
)
@click.pass_context
def extract(ctx, archive_path: str, file_path: str, output_dir: str):
    """Extract a single file from an archive."""
    from creation_lib.ba2 import native_runtime

    archive = Path(archive_path).expanduser().resolve(strict=False)
    if not archive.is_file():
        raise click.ClickException(f"Archive not found: {archive}")

    member = _normalize_member_path(file_path)
    out_dir = Path(output_dir).expanduser().resolve(strict=False)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = out_dir.joinpath(*member.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)

    data = native_runtime.extract_one(str(archive), member)
    target.write_bytes(data)

    output(
        {
            "archive": str(archive),
            "file": member,
            "written": str(target),
            "backend": "native",
        },
        _ctx_fmt(ctx),
    )


@archive.command("extract-all")
@click.argument("archive_path")
@click.option("--output-dir", required=True, help="Destination directory.")
@click.option("--workers", type=int, default=0, help="Worker count for native extraction.")
@click.pass_context
def extract_all(ctx, archive_path: str, output_dir: str, workers: int):
    """Extract an entire archive."""
    from creation_lib.ba2 import native_runtime

    archive = Path(archive_path).expanduser().resolve(strict=False)
    if not archive.is_file():
        raise click.ClickException(f"Archive not found: {archive}")

    out_dir = Path(output_dir).expanduser().resolve(strict=False)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = native_runtime.extract_archive(str(archive), str(out_dir), workers=max(0, workers))

    output(
        {
            "archive": str(archive),
            "output_dir": str(out_dir),
            "file_count": count,
            "backend": "native",
        },
        _ctx_fmt(ctx),
    )
