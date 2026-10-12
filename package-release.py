"""Package only clean distributable files; exclude history and model cache metadata."""
from pathlib import Path
from importlib import metadata
import shutil
import zipfile

root = Path(__file__).resolve().parent
bundle = root / 'dist' / 'NuffSaid'
if not (bundle / 'NuffSaid.exe').is_file():
    raise SystemExit('Run build-portable.ps1 first')

for distribution in metadata.distributions():
    name = distribution.metadata['Name']
    for relative in distribution.files or []:
        if ('licenses' in relative.parts or relative.name.lower().startswith(('license', 'copying'))) and '..' not in relative.parts:
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                dest = bundle / 'third-party-licenses' / name / str(relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)

runtime_license = Path(__import__('sys').base_prefix) / 'LICENSE.txt'
if runtime_license.exists():
    shutil.copy2(runtime_license, bundle / 'third-party-licenses' / 'Python-LICENSE.txt')

release = root / 'releases' / 'NuffSaid-Windows-x64.zip'
release.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(release, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for source in bundle.rglob('*'):
        relative = source.relative_to(bundle)
        if source.is_file() and relative.parts[0] != 'data' and not any(part in {'.cache', '__pycache__'} for part in relative.parts) and source.name != 'self-test.json':
            source = root / 'config-portable.yaml' if relative == Path('config.yaml') else source
            archive.write(source, Path('NuffSaid') / relative)
print(f'{release} ({release.stat().st_size / 1024**2:.1f} MiB)')
