from pathlib import Path

root = Path(SPECPATH)
package = root / "src" / "document_manager"
assets = [(str(path), path.parent.relative_to(root / "src").as_posix()) for path in (
    *package.joinpath("editor", "assets").glob("*"),
    *package.joinpath("presets").glob("*.json"),
    *package.joinpath("persistence", "migrations").glob("*.py"),
    *package.joinpath("persistence", "migrations").glob("*.mako"),
    *package.joinpath("persistence", "migrations", "versions").glob("*.py"),
) if path.is_file()]

analysis = Analysis(
    [str(package / "__main__.py")],
    pathex=[str(root / "src")],
    datas=assets,
    hiddenimports=["sqlalchemy.dialects.sqlite.pysqlite"],
)
archive = PYZ(analysis.pure)
exe = EXE(archive, analysis.scripts, [], exclude_binaries=True, name="919DocumentManager",
          console=False, upx=False)
dist = COLLECT(exe, analysis.binaries, analysis.datas, name="919DocumentManager", upx=False)
