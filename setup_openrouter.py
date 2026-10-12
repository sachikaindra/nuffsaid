"""Interactive local setup; never writes or prints the plaintext credential."""
import json
from pathlib import Path
import sys
import requests
import yaml
from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox
from openrouter_cleanup import BASE, MODEL, protect, cleanup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'dist' / 'NuffSaid' / 'data'


def main():
    app = QApplication(sys.argv)
    key, accepted = QInputDialog.getText(None, 'NuffSaid — OpenRouter setup',
        'Paste your OpenRouter API key here. It stays on this computer, encrypted.\n'
        'Setup sends a sample sentence to the free NVIDIA model to test cleanup.\n'
        'Your dictated text will be sent to OpenRouter when cleanup is enabled.',
        QLineEdit.EchoMode.Password)
    if not accepted or not key.strip():
        return
    key = key.strip()
    try:
        from run_flow import SYSTEM_PROMPT
        session = requests.Session()
        response = session.get(BASE + '/key', headers={'Authorization': 'Bearer ' + key},
                               timeout=10, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError('Key check failed (HTTP %s)' % response.status_code)
        quota = response.json()['data'].get('free_model_daily_requests', {})
        sample = "Um I will I will send Iyas the file tomorrow and then we can review it together."
        output, elapsed = cleanup(session, key, sample, SYSTEM_PROMPT)
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / 'openrouter.key.dpapi').write_bytes(protect(key.encode('utf-8')))
        for path in [ROOT / 'config.yaml', ROOT / 'dist' / 'NuffSaid' / 'config.yaml']:
            cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
            cfg['llm']['backend'] = 'openrouter'
            path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
        report = {'ok': True, 'model': MODEL, 'quota': quota, 'seconds': round(elapsed, 3),
                  'sample_input': sample, 'sample_output': output}
        (DATA / 'openrouter-setup-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        QMessageBox.information(None, 'NuffSaid — setup complete',
            f'Free cleanup tested in {elapsed:.2f} seconds.\n'
            f'Daily allowance: {quota.get("limit", "not reported")}\n\n'
            f'Sample result: {output}\n\nRestart NuffSaid to use OpenRouter.')
    except Exception as exc:
        # Only report controlled diagnostics; never dump server content or credentials.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        (DATA / 'openrouter-setup-result.json').write_text(json.dumps({'ok': False, 'error': message}))
        QMessageBox.warning(None, 'NuffSaid — setup not completed',
                            message + '\nThe existing cleanup configuration has been kept.')


if __name__ == '__main__':
    main()
